# Checklist — call-tracer 開發紀錄

每次做了什麼都在這裡更新。

---

## 2026-03-15（初始 Ralph Loop 執行）

### 目標
建立 code trace 整個流程的說明文件，讓使用者能理解整個 code flow。

### 完成項目

- [x] **探索整個 codebase 結構**
  - 讀取 `trace.py`, `tracer/cli.py`, `tracer/graph.py`, `tracer/analyzer.py`, `tracer/logic.py`
  - 讀取所有 parsers: `python_parser.py`, `javascript_parser.py`, `java_parser.py`, `c_parser.py`, `python_logic_parser.py`
  - 讀取所有 exporters: `plantuml_exporter.py`, `activity_exporter.py`, `sequence_exporter.py`
  - 讀取 `__init__.py` 確認匯出介面

- [x] **刪除 redundant 檔案**（根目錄的 output artifacts）
  - 刪除 `main.puml` — 上一次執行工具產生的 Call Graph 輸出
  - 刪除 `main_activity.puml` — 上一次執行工具產生的 Activity 輸出
  - 刪除 `main_sequence.puml` — 上一次執行工具產生的 Sequence 輸出
  - 原因：這三個是工具輸出物，不是原始碼，不應該放在專案根目錄

- [x] **建立 `./docs/` 目錄**

- [x] **建立 `./docs/usage.md`**（使用教學）
  - 包含：安裝、基本語法、所有參數說明
  - 8 個使用範例（從最基本到進階）
  - 三種圖表的詳細說明（Call Graph / Activity / Sequence）
  - PlantUML 渲染方式
  - 支援語言總表
  - 程式庫 API 用法
  - 專案結構

- [x] **建立 `./docs/checklist.md`**（此檔案）

---

## Codebase 架構總覽

```
使用者輸入 function name + path
        ↓
  cli.py: run()
        ↓
  _collect_source_files()   — 遞迴收集支援的原始碼檔案
        ↓
  build_graph()             — 建立 CallGraph
    ├── get_parser(file)    — 依副檔名選擇 Parser
    ├── parser.parse(file)  — 解析出 FunctionNode 列表
    ├── graph.add_node()    — 加入節點
    └── graph.resolve_edges() — 解析 raw call names → edges + call_order
        ↓
  analyze(graph, function)  — 雙向 BFS 追蹤
    ├── backward_trace()    — 往上：誰呼叫它（BFS）
    └── forward_trace()     — 往下：它呼叫誰（BFS）
        ↓
  輸出三種圖表：
    ├── PlantUMLExporter    → <name>.puml          Call Graph
    ├── ActivityExporter    → <name>_activity.puml  Logic Flow
    │     └── PythonLogicParser → FunctionBody     （Python only）
    └── SequenceExporter    → <name>_sequence.puml  Caller Chain
```

---

## Activity Diagram 邏輯覆蓋（Python）

| 程式碼結構 | logic.py 型別 | activity_exporter.py 處理 |
|-----------|--------------|--------------------------|
| 函式呼叫 | `CallStmt` | 藍色 action box |
| 賦值 | `AssignStmt` | 灰色 action box |
| return | `ReturnStmt` | 綠色 terminal |
| raise | `RaiseStmt` | 紅色 terminal |
| assert | `AssertStmt` | 菱形 if/fail |
| break | `BreakStmt` | 橘色 action box |
| continue | `ContinueStmt` | 紫色 action box |
| if/elif/else | `IfBlock` | if/elseif/else/endif |
| for loop | `ForBlock` | while/endwhile |
| while loop | `WhileBlock` | while/endwhile |
| try/except/finally | `TryBlock` | partition 區塊 |
| match/case | `SwitchBlock` | partition + if/elseif 鏈 |

---

---

## 2026-03-16（Ralph Loop Iteration 1）

### 目標
- Sequence diagram 顯示雙向流程（callers 往上 + callees 往下），附帶 return 箭頭與參數
- 刪除多餘的輸出 .puml 檔案
- 更新 docs

### 完成項目

- [x] **刪除多餘 .puml 輸出檔**
  - 刪除根目錄 `main.puml`, `main_activity.puml`, `main_sequence.puml`

- [x] **重寫 `tracer/exporters/sequence_exporter.py`（雙向 sequence diagram）**
  - 舊版：只顯示 caller 鏈（往上），無 return 箭頭
  - 新版：
    - 往上：caller chain → TARGET（call 箭頭 + 參數）
    - 往下：TARGET → callees → sub-callees（DFS，按 source order）
    - 所有 call 箭頭含 `[seq]` 序號與 args
    - 所有 return 箭頭用虛線 `-->`
  - 演算法：Phase 1（callers call down） → Phase 2（target calls forward tree） → Phase 3（return back up callers）

- [x] **新增 `--forward-depth N` CLI 參數**
  - 控制往下顯示幾層 callees（預設 3）
  - 傳入 `SequenceExporter.export(forward_depth=N)`

- [x] **更新 `tracer/cli.py`**
  - `_generate_sequence_diagram()` 加入 `forward_depth` 參數
  - 呼叫點傳入 `opts.forward_depth`

- [x] **新增 `tracer/parsers/c_logic_parser.py`**（前次迭代補記）
  - 使用 libclang 解析 C/C++ AST
  - 完整支援 if/elif/else、for、while、do-while、switch/case、return、break、continue
  - `pip install libclang` 安裝；未安裝時 graceful fallback

- [x] **Activity diagram 顏色格式修正**（前次迭代補記）
  - 從 `:label; #COLOR` 改為 `#COLOR:label;`（PlantUML 標準格式）

- [x] **更新 `docs/usage.md`**
  - 參數表加入 `--forward-depth`
  - Sequence diagram 說明改為雙向格式
  - C/C++ Activity 圖支援狀態改為 ✅

---

## 待辦 / 已知限制

- [ ] C/C++ parser（`c_parser.py`）不提取函式呼叫的 argument 值，sequence diagram 中 C/C++ 函式的 args 欄位為空
- [ ] `python_logic_parser.py` line 226: `stmt.finalbody` — Python AST `ast.Try` 的 `finalbody` 在 3.11+ 需確認相容性
