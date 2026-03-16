"""Standalone C/C++ logic parser — no external dependencies.

Provides a regex-based tokenizer and recursive-descent parser that
converts C source code into FunctionBody AST nodes from tracer.logic.

Unlike c_logic_parser.py (which requires libclang), this parser works
standalone and is the default for C/C++ logic-flow sequence diagrams.
"""

import re
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

from ..logic import (
    FunctionBody, CallStmt, AssignStmt, ReturnStmt,
    BreakStmt, ContinueStmt, GotoStmt, LabelStmt,
    IfBlock, ForBlock, WhileBlock, SwitchBlock, SwitchCase,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Tokenizer
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Token:
    type: str
    value: str
    line: int
    col: int


_TOKEN_SPEC = [
    ('BLOCK_COMMENT', r'/\*[\s\S]*?\*/'),
    ('LINE_COMMENT',  r'//[^\n]*'),
    ('PREPROC',       r'#[^\n]*'),
    ('STRING',        r'"(?:[^"\\]|\\.)*"'),
    ('CHAR_LIT',      r"'(?:[^'\\]|\\.)*'"),
    ('FLOAT',         r'\d+\.\d*(?:[eE][+-]?\d+)?[fFlL]?'),
    ('HEX',           r'0[xX][0-9a-fA-F]+[uUlL]*'),
    ('INT',           r'\d+[uUlL]*'),
    # Multi-char operators (longest first)
    ('ARROW',         r'->'),
    ('INCR',          r'\+\+'),
    ('DECR',          r'--'),
    ('LSHIFT_ASSIGN', r'<<='),
    ('RSHIFT_ASSIGN', r'>>='),
    ('LSHIFT',        r'<<'),
    ('RSHIFT',        r'>>'),
    ('LE',            r'<='),
    ('GE',            r'>='),
    ('EQ',            r'=='),
    ('NEQ',           r'!='),
    ('AND',           r'&&'),
    ('OR',            r'\|\|'),
    ('PLUS_ASSIGN',   r'\+='),
    ('MINUS_ASSIGN',  r'-='),
    ('STAR_ASSIGN',   r'\*='),
    ('SLASH_ASSIGN',  r'/='),
    ('PERCENT_ASSIGN', r'%='),
    ('AND_ASSIGN',    r'&='),
    ('OR_ASSIGN',     r'\|='),
    ('XOR_ASSIGN',    r'\^='),
    # Single-char
    ('LBRACE',        r'\{'),
    ('RBRACE',        r'\}'),
    ('LPAREN',        r'\('),
    ('RPAREN',        r'\)'),
    ('LBRACKET',      r'\['),
    ('RBRACKET',      r'\]'),
    ('SEMI',          r';'),
    ('COMMA',         r','),
    ('COLON',         r':'),
    ('QUESTION',      r'\?'),
    ('DOT',           r'\.'),
    ('PLUS',          r'\+'),
    ('MINUS',         r'-'),
    ('STAR',          r'\*'),
    ('SLASH',         r'/'),
    ('PERCENT',       r'%'),
    ('ASSIGN',        r'='),
    ('LT',            r'<'),
    ('GT',            r'>'),
    ('NOT',           r'!'),
    ('BIT_AND',       r'&'),
    ('BIT_OR',        r'\|'),
    ('BIT_XOR',       r'\^'),
    ('BIT_NOT',       r'~'),
    ('IDENT',         r'[a-zA-Z_]\w*'),
    ('NEWLINE',       r'\n'),
    ('SKIP',          r'[ \t\r]+'),
    ('MISMATCH',      r'.'),
]

_MASTER_RE = re.compile(
    '|'.join(f'(?P<{name}>{pat})' for name, pat in _TOKEN_SPEC)
)

_C_KEYWORDS = {
    'if': 'IF', 'else': 'ELSE', 'for': 'FOR', 'while': 'WHILE', 'do': 'DO',
    'switch': 'SWITCH', 'case': 'CASE', 'default': 'DEFAULT',
    'break': 'BREAK', 'continue': 'CONTINUE', 'return': 'RETURN', 'goto': 'GOTO',
    'struct': 'STRUCT', 'enum': 'ENUM', 'union': 'UNION', 'typedef': 'TYPEDEF',
    'sizeof': 'SIZEOF',
    'const': 'CONST', 'static': 'STATIC', 'extern': 'EXTERN',
    'inline': 'INLINE', 'volatile': 'VOLATILE',
}

# Type keywords recognised for variable declaration detection
_TYPE_KEYWORDS = frozenset({
    'void', 'int', 'char', 'short', 'long', 'float', 'double',
    'unsigned', 'signed', 'bool', 'size_t', 'ssize_t',
    'int8_t', 'int16_t', 'int32_t', 'int64_t',
    'uint8_t', 'uint16_t', 'uint32_t', 'uint64_t',
    'FILE', 'wchar_t', 'ptrdiff_t', 'true', 'false', 'NULL',
})

_QUALIFIER_KEYWORDS = frozenset({'const', 'static', 'extern', 'inline', 'volatile'})

# Control-flow keywords that look like function calls but aren't
_SKIP_CALL_KEYWORDS = frozenset({
    'if', 'for', 'while', 'switch', 'do', 'catch', 'return',
    'sizeof', 'typeof', 'alignof', 'new', 'delete', 'throw',
    'static_cast', 'dynamic_cast', 'reinterpret_cast', 'const_cast',
})


def tokenize(source: str) -> List[Token]:
    """Tokenize C source code. Returns list of Token (including comments)."""
    tokens: List[Token] = []
    line = 1
    line_start = 0

    for m in _MASTER_RE.finditer(source):
        kind = m.lastgroup
        value = m.group()
        start = m.start()
        col = start - line_start + 1

        if kind == 'NEWLINE':
            line += 1
            line_start = m.end()
            continue
        if kind == 'SKIP':
            continue
        if kind == 'MISMATCH':
            continue

        # Count newlines inside block comments
        if kind == 'BLOCK_COMMENT':
            nl = value.count('\n')
            if nl:
                line += nl
                line_start = start + value.rfind('\n') + 1

        # Classify identifiers
        if kind == 'IDENT':
            if value in _C_KEYWORDS:
                kind = _C_KEYWORDS[value]
            elif value in _TYPE_KEYWORDS:
                kind = 'TYPE_KW'
            # else remains IDENT

        # Normalise literal types
        if kind in ('HEX', 'FLOAT', 'INT'):
            kind = 'NUMBER'
        if kind == 'CHAR_LIT':
            kind = 'STRING'

        tokens.append(Token(type=kind, value=value, line=line, col=col))

    tokens.append(Token(type='EOF', value='', line=line, col=0))
    return tokens


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: reconstruct text from tokens
# ═══════════════════════════════════════════════════════════════════════════════

_NO_SPACE_BEFORE = frozenset({
    'RPAREN', 'RBRACKET', 'LBRACKET', 'COMMA', 'SEMI', 'COLON', 'DOT',
    'ARROW', 'INCR', 'DECR',
})
_NO_SPACE_AFTER = frozenset({
    'LPAREN', 'LBRACKET', 'DOT', 'ARROW', 'NOT', 'BIT_NOT',
})


def _tokens_text(tokens: List[Token]) -> str:
    """Join tokens into readable text with reasonable spacing."""
    if not tokens:
        return ""
    parts: List[str] = [tokens[0].value]
    for i in range(1, len(tokens)):
        prev, cur = tokens[i - 1], tokens[i]
        need_space = True
        if cur.type in _NO_SPACE_BEFORE:
            need_space = False
        elif prev.type in _NO_SPACE_AFTER:
            need_space = False
        elif prev.value == '&' and cur.type in ('IDENT', 'TYPE_KW'):
            need_space = False  # &variable
        elif prev.type == 'STAR' and cur.type in ('IDENT', 'TYPE_KW', 'STAR'):
            # Likely dereference: *val, **ptr  (not multiplication: a * b)
            if i < 2 or tokens[i - 2].type in (
                'LPAREN', 'LBRACKET', 'COMMA', 'SEMI', 'ASSIGN',
                'PLUS_ASSIGN', 'MINUS_ASSIGN', 'STAR_ASSIGN',
                'SLASH_ASSIGN', 'PERCENT_ASSIGN', 'RETURN',
                'EQ', 'NEQ', 'LT', 'GT', 'LE', 'GE', 'AND', 'OR',
                'NOT', 'COLON', 'QUESTION', 'LBRACE',
            ):
                need_space = False
        # Unary minus: no space between '-' and number/ident when preceded by
        # operator, '(', '[', '=', ',' or at start
        elif cur.type in ('NUMBER', 'IDENT', 'TYPE_KW') and prev.value == '-':
            if i >= 2:
                pp = tokens[i - 2]
                if pp.type in ('LPAREN', 'LBRACKET', 'COMMA', 'ASSIGN',
                               'PLUS_ASSIGN', 'MINUS_ASSIGN', 'STAR_ASSIGN',
                               'SLASH_ASSIGN', 'PERCENT_ASSIGN', 'EQ', 'NEQ',
                               'LT', 'GT', 'LE', 'GE', 'AND', 'OR',
                               'RETURN', 'COLON', 'QUESTION', 'SEMI'):
                    need_space = False
            else:
                need_space = False  # '-' is the first token → unary
        if need_space:
            parts.append(' ')
        parts.append(cur.value)
    return ''.join(parts)


def _extract_comment_text(tok: Token) -> str:
    """Strip comment delimiters and return clean text."""
    v = tok.value
    if v.startswith('//'):
        return v[2:].strip()
    if v.startswith('/*'):
        return v[2:-2].strip()
    return v.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# Function info (lightweight metadata before deep parsing)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FuncInfo:
    """Lightweight descriptor of a function found in the source."""
    name: str
    return_type: str
    params_text: str
    body_start: int   # token index of opening '{'
    body_end: int      # token index of closing '}'
    line: int
    doc_comment: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Parser
# ═══════════════════════════════════════════════════════════════════════════════

class CFlowParser:
    """Standalone recursive-descent C parser for logic-flow extraction."""

    def __init__(self, source: str, file_path: str):
        self.source = source
        self.file_path = os.path.abspath(file_path)
        all_tokens = tokenize(source)
        # Separate comments from code tokens; keep track for association
        self.tokens: List[Token] = []
        self._comments: Dict[int, List[Token]] = {}  # code_token_idx -> preceding comments
        pending_comments: List[Token] = []
        for tok in all_tokens:
            if tok.type in ('LINE_COMMENT', 'BLOCK_COMMENT'):
                pending_comments.append(tok)
            elif tok.type == 'PREPROC':
                pending_comments.clear()  # preprocessor resets comment context
            else:
                idx = len(self.tokens)
                if pending_comments:
                    self._comments[idx] = list(pending_comments)
                    pending_comments.clear()
                self.tokens.append(tok)
        self.pos = 0

    # ── Token navigation ──────────────────────────────────────────────────────

    def _peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]  # EOF

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def _check(self, *types: str) -> bool:
        return self._peek().type in types

    def _expect(self, tp: str) -> Token:
        tok = self._peek()
        if tok.type != tp:
            # Recovery: skip to expected token or give up
            return tok
        return self._advance()

    def _at_end(self) -> bool:
        return self._peek().type == 'EOF'

    def _get_comment(self) -> Optional[str]:
        """Get any comments associated with the current token position."""
        comments = self._comments.get(self.pos)
        if comments:
            return ' '.join(_extract_comment_text(c) for c in comments)
        return None

    # ── Top-level: find all function definitions ──────────────────────────────

    def find_all_functions(self) -> List[FuncInfo]:
        """Scan tokens to find all function definitions."""
        self.pos = 0
        funcs: List[FuncInfo] = []

        while not self._at_end():
            info = self._try_parse_func_def()
            if info:
                funcs.append(info)
            else:
                self._advance()

        return funcs

    def _try_parse_func_def(self) -> Optional[FuncInfo]:
        """Try to match a function definition at current position.
        Pattern: [qualifiers/type] name ( params ) {
        """
        save = self.pos
        doc_comment = self._get_comment() or ""

        # Collect return type tokens (qualifiers + type specifiers + pointer stars)
        type_tokens: List[Token] = []
        while self._check('CONST', 'STATIC', 'EXTERN', 'INLINE', 'VOLATILE',
                          'STRUCT', 'ENUM', 'UNION', 'TYPE_KW', 'IDENT',
                          'STAR', 'UNSIGNED', 'SIGNED'):
            # Look ahead: if this IDENT is followed by '(', it might be the func name
            if self._check('IDENT', 'TYPE_KW'):
                if self._peek(1).type == 'LPAREN':
                    break  # This IDENT is the function name
                # Check if this IDENT is followed by STAR then IDENT (like int *foo)
                if self._peek(1).type == 'STAR':
                    type_tokens.append(self._advance())
                    continue
                # Check if this IDENT is followed by another IDENT (like unsigned int)
                if self._peek(1).type in ('IDENT', 'TYPE_KW'):
                    type_tokens.append(self._advance())
                    continue
            type_tokens.append(self._advance())

        if not type_tokens:
            self.pos = save
            return None

        # Expect function name (IDENT) followed by '('
        if not self._check('IDENT', 'TYPE_KW'):
            self.pos = save
            return None

        name_tok = self._peek()
        if self._peek(1).type != 'LPAREN':
            self.pos = save
            return None

        # Skip control-flow keywords that look like func calls
        if name_tok.value in _SKIP_CALL_KEYWORDS:
            self.pos = save
            return None

        func_name = self._advance().value  # consume name
        self._advance()  # consume '('

        # Collect parameter tokens until matching ')'
        params_tokens: List[Token] = []
        depth = 1
        while depth > 0 and not self._at_end():
            tok = self._advance()
            if tok.type == 'LPAREN':
                depth += 1
            elif tok.type == 'RPAREN':
                depth -= 1
                if depth == 0:
                    break
            params_tokens.append(tok)

        # After ')' there might be const/noexcept/override, then must be '{'
        while self._check('CONST', 'VOLATILE', 'IDENT'):
            self._advance()

        if not self._check('LBRACE'):
            self.pos = save
            return None

        body_start = self.pos
        self._advance()  # consume '{'

        # Find matching '}'
        depth = 1
        while depth > 0 and not self._at_end():
            tok = self._advance()
            if tok.type == 'LBRACE':
                depth += 1
            elif tok.type == 'RBRACE':
                depth -= 1

        body_end = self.pos - 1

        return FuncInfo(
            name=func_name,
            return_type=_tokens_text(type_tokens),
            params_text=_tokens_text(params_tokens),
            body_start=body_start,
            body_end=body_end,
            line=name_tok.line,
            doc_comment=doc_comment,
        )

    # ── Parse a specific function's body ──────────────────────────────────────

    def parse_function(self, func_name: str) -> Optional[FunctionBody]:
        """Parse the body of the named function into a FunctionBody."""
        funcs = self.find_all_functions()
        target = None
        for f in funcs:
            if f.name == func_name:
                target = f
                break

        if target is None:
            return None

        # Position at the '{' of the function body and parse
        self.pos = target.body_start
        self._advance()  # skip opening '{'

        stmts = self._parse_block_body(target.body_end)

        # Extract param names from params_text
        params = self._extract_param_names(target.params_text)

        return FunctionBody(
            qualified_name=func_name,
            file=self.file_path,
            line=target.line,
            language="c/c++",
            params=params,
            statements=stmts,
        )

    def _extract_param_names(self, params_text: str) -> List[str]:
        """Extract parameter names from a C function parameter list."""
        if not params_text.strip() or params_text.strip() == 'void':
            return []
        params = []
        for part in params_text.split(','):
            part = part.strip()
            if not part:
                continue
            # Remove pointer stars and array brackets for the name
            # Last word token is the parameter name
            words = re.findall(r'[a-zA-Z_]\w*', part)
            if words:
                params.append(words[-1])
        return params

    # ── Block parsing (statements between braces) ─────────────────────────────

    def _parse_block_body(self, end_pos: int) -> List:
        """Parse statements until reaching end_pos (the closing '}')."""
        stmts: List = []
        while self.pos < end_pos and not self._at_end():
            if self._check('RBRACE'):
                break
            stmt = self._parse_statement()
            if stmt is not None:
                stmts.append(stmt)
        return stmts

    def _parse_brace_block(self) -> List:
        """Parse a { ... } block, returning the list of statements inside."""
        if not self._check('LBRACE'):
            # Single statement (no braces)
            stmt = self._parse_statement()
            return [stmt] if stmt else []

        self._advance()  # consume '{'
        stmts: List = []
        while not self._check('RBRACE') and not self._at_end():
            stmt = self._parse_statement()
            if stmt is not None:
                stmts.append(stmt)
        if self._check('RBRACE'):
            self._advance()  # consume '}'
        return stmts

    # ── Statement dispatcher ──────────────────────────────────────────────────

    def _parse_statement(self) -> Optional[object]:  # noqa: C901
        comment = self._get_comment()
        tok = self._peek()

        if tok.type == 'LBRACE':
            stmts = self._parse_brace_block()
            return stmts[0] if len(stmts) == 1 else None

        if tok.type == 'IF':
            return self._parse_if(comment)

        if tok.type == 'FOR':
            return self._parse_for(comment)

        if tok.type == 'WHILE':
            return self._parse_while(comment)

        if tok.type == 'DO':
            return self._parse_do_while(comment)

        if tok.type == 'SWITCH':
            return self._parse_switch(comment)

        if tok.type == 'RETURN':
            return self._parse_return()

        if tok.type == 'BREAK':
            self._advance()
            self._skip_semi()
            return BreakStmt()

        if tok.type == 'CONTINUE':
            self._advance()
            self._skip_semi()
            return ContinueStmt()

        if tok.type == 'GOTO':
            return self._parse_goto(comment)

        # Label: IDENT followed by ':' (but not CASE/DEFAULT which are handled by switch)
        if tok.type == 'IDENT' and self._peek(1).type == 'COLON':
            name = self._advance().value
            self._advance()  # consume ':'
            return LabelStmt(name=name)

        # Variable declaration or expression statement
        if self._is_var_decl():
            return self._parse_var_decl(comment)

        return self._parse_expr_stmt(comment)

    def _skip_semi(self):
        if self._check('SEMI'):
            self._advance()

    # ── Control flow parsers ──────────────────────────────────────────────────

    def _parse_if(self, comment: str = None) -> IfBlock:
        self._expect('IF')
        condition = self._collect_paren_text()

        # Check for comment right after the opening brace
        then_body = self._parse_brace_block()

        elif_clauses: List[Tuple[str, List]] = []
        else_body: List = []

        while self._check('ELSE'):
            self._advance()  # consume 'else'
            if self._check('IF'):
                self._advance()  # consume 'if'
                elif_cond = self._collect_paren_text()
                elif_body = self._parse_brace_block()
                elif_clauses.append((elif_cond, elif_body))
            else:
                else_body = self._parse_brace_block()
                break

        return IfBlock(
            condition=condition,
            then_body=then_body,
            elif_clauses=elif_clauses,
            else_body=else_body,
        )

    def _parse_for(self, comment: str = None) -> WhileBlock:
        self._expect('FOR')
        self._expect('LPAREN')

        # Collect three parts: init; condition; update
        init_toks = self._collect_until_semi()
        self._skip_semi()
        cond_toks = self._collect_until_semi()
        self._skip_semi()
        update_toks = self._collect_until_rparen()
        self._expect('RPAREN')

        # Build description
        init_text = _tokens_text(init_toks).strip()
        cond_text = _tokens_text(cond_toks).strip()
        update_text = _tokens_text(update_toks).strip()

        # Build a readable for-loop description
        loop_desc = f"for ({init_text}; {cond_text}; {update_text})"

        # Check for body comment
        body_comment = self._get_comment()
        if body_comment:
            loop_desc += f" ({body_comment})"
        elif comment:
            loop_desc += f" ({comment})"

        body = self._parse_brace_block()

        return WhileBlock(condition=loop_desc, body=body)

    def _parse_while(self, comment: str = None) -> WhileBlock:
        self._expect('WHILE')
        condition = self._collect_paren_text()

        body_comment = self._get_comment()
        desc = condition
        if body_comment:
            desc += f" ({body_comment})"
        elif comment:
            desc += f" ({comment})"

        body = self._parse_brace_block()
        return WhileBlock(condition=desc, body=body)

    def _parse_do_while(self, comment: str = None) -> WhileBlock:
        self._expect('DO')
        body = self._parse_brace_block()
        self._expect('WHILE')
        condition = self._collect_paren_text()
        self._skip_semi()
        return WhileBlock(condition=f"do-while ({condition})", body=body)

    def _parse_switch(self, comment: str = None) -> SwitchBlock:
        self._expect('SWITCH')
        subject = self._collect_paren_text()
        self._expect('LBRACE')

        cases: List[SwitchCase] = []
        while not self._check('RBRACE') and not self._at_end():
            case_comment = self._get_comment()

            if self._check('CASE'):
                self._advance()  # consume 'case'
                value_toks = self._collect_until_colon()
                self._expect('COLON')
                body = self._parse_case_body()
                cases.append(SwitchCase(
                    pattern=_tokens_text(value_toks).strip(),
                    body=body,
                ))

            elif self._check('DEFAULT'):
                self._advance()  # consume 'default'
                self._expect('COLON')
                body = self._parse_case_body()
                cases.append(SwitchCase(
                    pattern='default',
                    body=body,
                    is_default=True,
                ))
            else:
                self._advance()  # skip unexpected token

        if self._check('RBRACE'):
            self._advance()

        return SwitchBlock(subject=subject, cases=cases)

    def _parse_case_body(self) -> List:
        """Parse statements within a case clause until next case/default/}."""
        stmts: List = []
        while not self._check('CASE', 'DEFAULT', 'RBRACE') and not self._at_end():
            stmt = self._parse_statement()
            if stmt is not None:
                stmts.append(stmt)
        return stmts

    def _parse_return(self) -> ReturnStmt:
        self._expect('RETURN')
        if self._check('SEMI'):
            self._advance()
            return ReturnStmt(value="")

        expr_toks = self._collect_until_semi()
        self._skip_semi()
        return ReturnStmt(value=_tokens_text(expr_toks).strip())

    def _parse_goto(self, comment: str = None) -> GotoStmt:
        self._expect('GOTO')
        label = self._advance().value if self._check('IDENT') else "?"
        self._skip_semi()
        return GotoStmt(label=label, comment=comment or "")

    # ── Variable declaration parsing ──────────────────────────────────────────

    def _is_var_decl(self) -> bool:
        """Heuristic: current position starts a variable declaration."""
        tok = self._peek()
        if tok.type in ('TYPE_KW', 'CONST', 'STATIC', 'EXTERN', 'VOLATILE',
                        'STRUCT', 'ENUM', 'UNION'):
            return True
        return False

    def _parse_var_decl(self, comment: str = None):
        """Parse a variable declaration: type [*] name [= expr] ;"""
        # Collect type tokens
        type_toks: List[Token] = []
        while self._check('TYPE_KW', 'CONST', 'STATIC', 'EXTERN', 'VOLATILE',
                          'STRUCT', 'ENUM', 'UNION', 'IDENT', 'STAR',
                          'UNSIGNED', 'SIGNED'):
            # Stop if this IDENT is followed by '=' or ';' or ',' (it's the var name)
            if self._check('IDENT', 'TYPE_KW'):
                next_t = self._peek(1).type
                if next_t in ('ASSIGN', 'SEMI', 'COMMA', 'LBRACKET',
                              'PLUS_ASSIGN', 'MINUS_ASSIGN', 'STAR_ASSIGN'):
                    break
                # If next is IDENT, current is still part of the type
                if next_t in ('IDENT', 'TYPE_KW', 'STAR'):
                    type_toks.append(self._advance())
                    continue
            if self._check('STAR'):
                type_toks.append(self._advance())
                continue
            type_toks.append(self._advance())

        # Now expect the variable name
        if not self._check('IDENT', 'TYPE_KW'):
            # Failed to parse, skip to semicolon
            self._skip_to_semi()
            return None

        var_name = self._advance().value

        # Skip array brackets
        while self._check('LBRACKET'):
            self._advance()
            while not self._check('RBRACKET') and not self._at_end():
                self._advance()
            if self._check('RBRACKET'):
                self._advance()

        # Check for initializer
        if self._check('ASSIGN'):
            self._advance()  # consume '='
            # Check if RHS is a function call
            if self._check('IDENT') and self._peek(1).type == 'LPAREN':
                func_name = self._peek().value
                if func_name not in _SKIP_CALL_KEYWORDS:
                    call = self._parse_call_expr()
                    if call:
                        call.assigned_to = var_name
                        self._skip_semi()
                        return call

            init_toks = self._collect_until_semi()
            self._skip_semi()
            return AssignStmt(
                target=var_name,
                value=_tokens_text(init_toks).strip(),
            )

        self._skip_semi()
        # Declaration without initializer — skip for diagram purposes
        return None

    # ── Expression statement parsing ──────────────────────────────────────────

    def _parse_expr_stmt(self, comment: str = None):
        """Parse an expression statement (assignment, function call, etc.)."""
        # Check for direct function call: IDENT ( ... ) ;
        if self._check('IDENT') and self._peek(1).type == 'LPAREN':
            func_name = self._peek().value
            if func_name not in _SKIP_CALL_KEYWORDS:
                call = self._parse_call_expr()
                if call:
                    self._skip_semi()
                    return call

        # Check for assignment: expr = expr ;  or  expr op= expr ;
        # or compound expressions like *val *= 2;
        expr_toks = self._collect_until_semi()
        self._skip_semi()

        if not expr_toks:
            return None

        text = _tokens_text(expr_toks).strip()
        if not text:
            return None

        # Try to split at assignment operator
        assign_types = {
            'ASSIGN', 'PLUS_ASSIGN', 'MINUS_ASSIGN', 'STAR_ASSIGN',
            'SLASH_ASSIGN', 'PERCENT_ASSIGN', 'AND_ASSIGN', 'OR_ASSIGN',
            'XOR_ASSIGN', 'LSHIFT_ASSIGN', 'RSHIFT_ASSIGN',
        }

        # Find the assignment operator (not inside parens/brackets)
        depth = 0
        for i, tok in enumerate(expr_toks):
            if tok.type in ('LPAREN', 'LBRACKET'):
                depth += 1
            elif tok.type in ('RPAREN', 'RBRACKET'):
                depth -= 1
            elif depth == 0 and tok.type in assign_types:
                lhs = _tokens_text(expr_toks[:i]).strip()
                rhs_toks = expr_toks[i + 1:]
                # Check if RHS contains a function call
                rhs_call = self._find_call_in_tokens(rhs_toks)
                if rhs_call:
                    rhs_call.assigned_to = lhs
                    return rhs_call

                rhs = _tokens_text(rhs_toks).strip()
                if tok.type != 'ASSIGN':
                    # Augmented assignment: store as whole expression
                    # e.g. status += 10 → target="status += 10", value=""
                    return AssignStmt(target=text, value="")
                return AssignStmt(target=lhs, value=rhs)

        # Check for standalone expression with function call
        call = self._find_call_in_tokens(expr_toks)
        if call:
            return call

        # Fallback: standalone expression (i++, --x, etc.)
        return AssignStmt(target=text, value="")

    def _parse_call_expr(self) -> Optional[CallStmt]:
        """Parse: IDENT ( args ) — returns CallStmt or None."""
        if not self._check('IDENT'):
            return None
        func_name = self._advance().value
        if not self._check('LPAREN'):
            return None
        self._advance()  # consume '('

        args: List[str] = []
        if not self._check('RPAREN'):
            args = self._collect_call_args()

        if self._check('RPAREN'):
            self._advance()

        return CallStmt(name=func_name, args=args)

    def _collect_call_args(self) -> List[str]:
        """Collect comma-separated arguments, respecting nesting."""
        args: List[str] = []
        current: List[Token] = []
        depth = 0

        while not self._at_end():
            tok = self._peek()
            if tok.type == 'RPAREN' and depth == 0:
                break
            if tok.type in ('LPAREN', 'LBRACKET', 'LBRACE'):
                depth += 1
            elif tok.type in ('RPAREN', 'RBRACKET', 'RBRACE'):
                depth -= 1
            elif tok.type == 'COMMA' and depth == 0:
                args.append(_tokens_text(current).strip())
                current = []
                self._advance()
                continue
            current.append(self._advance())

        if current:
            args.append(_tokens_text(current).strip())
        return args

    def _find_call_in_tokens(self, toks: List[Token]) -> Optional[CallStmt]:
        """Find first function call pattern in a list of tokens."""
        for i, tok in enumerate(toks):
            if (tok.type == 'IDENT'
                    and tok.value not in _SKIP_CALL_KEYWORDS
                    and i + 1 < len(toks)
                    and toks[i + 1].type == 'LPAREN'):
                # Found: name(
                name = tok.value
                # Collect args
                depth = 0
                arg_toks: List[Token] = []
                j = i + 2  # skip name and '('
                while j < len(toks):
                    t = toks[j]
                    if t.type == 'LPAREN':
                        depth += 1
                    elif t.type == 'RPAREN':
                        if depth == 0:
                            break
                        depth -= 1
                    arg_toks.append(t)
                    j += 1

                args_text = _tokens_text(arg_toks).strip()
                args = [a.strip() for a in self._split_args_text(args_text)] if args_text else []
                return CallStmt(name=name, args=args)
        return None

    def _split_args_text(self, text: str) -> List[str]:
        """Split argument text by commas, respecting nesting."""
        args: List[str] = []
        depth = 0
        current = []
        for ch in text:
            if ch in ('(', '[', '{'):
                depth += 1
            elif ch in (')', ']', '}'):
                depth -= 1
            elif ch == ',' and depth == 0:
                args.append(''.join(current).strip())
                current = []
                continue
            current.append(ch)
        if current:
            args.append(''.join(current).strip())
        return args

    # ── Token collection helpers ──────────────────────────────────────────────

    def _collect_paren_text(self) -> str:
        """Consume ( ... ) and return the text inside."""
        self._expect('LPAREN')
        toks: List[Token] = []
        depth = 1
        while depth > 0 and not self._at_end():
            tok = self._advance()
            if tok.type == 'LPAREN':
                depth += 1
            elif tok.type == 'RPAREN':
                depth -= 1
                if depth == 0:
                    break
            toks.append(tok)
        return _tokens_text(toks).strip()

    def _collect_until_semi(self) -> List[Token]:
        """Collect tokens until ';', respecting nesting."""
        toks: List[Token] = []
        depth = 0
        while not self._at_end():
            tok = self._peek()
            if tok.type == 'SEMI' and depth == 0:
                break
            if tok.type in ('LPAREN', 'LBRACKET', 'LBRACE'):
                depth += 1
            elif tok.type in ('RPAREN', 'RBRACKET', 'RBRACE'):
                depth -= 1
                if depth < 0:
                    break
            toks.append(self._advance())
        return toks

    def _collect_until_rparen(self) -> List[Token]:
        """Collect tokens until ')' at depth 0."""
        toks: List[Token] = []
        depth = 0
        while not self._at_end():
            tok = self._peek()
            if tok.type == 'RPAREN' and depth == 0:
                break
            if tok.type == 'LPAREN':
                depth += 1
            elif tok.type == 'RPAREN':
                depth -= 1
            toks.append(self._advance())
        return toks

    def _collect_until_colon(self) -> List[Token]:
        """Collect tokens until ':' at depth 0."""
        toks: List[Token] = []
        depth = 0
        while not self._at_end():
            tok = self._peek()
            if tok.type == 'COLON' and depth == 0:
                break
            if tok.type in ('LPAREN', 'LBRACKET'):
                depth += 1
            elif tok.type in ('RPAREN', 'RBRACKET'):
                depth -= 1
            toks.append(self._advance())
        return toks

    def _skip_to_semi(self):
        """Skip tokens until ';' is consumed."""
        while not self._at_end():
            if self._advance().type == 'SEMI':
                return


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def parse_c_file(file_path: str):
    """Parse a C file and return (parser, all_func_infos).

    Returns:
        parser: CFlowParser instance (call parser.parse_function(name))
        funcs:  list of FuncInfo for all functions in the file
    """
    with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
        source = fh.read()
    parser = CFlowParser(source, file_path)
    funcs = parser.find_all_functions()
    return parser, funcs
