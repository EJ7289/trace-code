# call-tracer 使用教學

## 簡介

`call-tracer` 是一個跨語言雙向函式呼叫追蹤工具，輸入一個函式名稱後自動產生三種 PlantUML 圖表：

| 圖表 | 檔案 | 說明 |
|------|------|------|
| Call Graph | `<name>.puml` | 誰呼叫它 + 它呼叫誰（雙向呼叫圖） |
| Activity / Logic Flow | `<name>_activity.puml` | 函式內部邏輯：if/else/while/try/return/raise |
| Caller Sequence | `<name>_sequence.puml` | 呼叫者鏈（誰呼叫它，帶參數） |

---

## 安裝

```bash
# 安裝為套件（推薦）
pip install -e .

# 或直接執行（不需安裝）
python trace.py <args>
```

---

## 基本語法

```
tracer <function_name> <path...> [options]
```

---

## 參數說明

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `function` | 目標函式名稱（可用 `ClassName.method` 精確指定） | 必填 |
| `PATH ...` | 原始碼檔案或目錄（目錄會遞迴掃描） | 必填 |
| `--depth N` / `-d N` | 追蹤層數（forward + backward） | 不限 |
| `--seq-depth N` | Sequence diagram 顯示**往上** caller 層數 | 5 |
| `--forward-depth N` | Sequence diagram 顯示**往下** callee 層數 | 3 |
| `--output FILE` / `-o FILE` | 輸出 `.puml` 的基底路徑 | `<function>.puml` |
| `--no-files` | 圖表節點不顯示檔案與行號 | - |
| `--no-activity` | 不產生 activity 圖 | - |
| `--no-sequence` | 不產生 sequence 圖 | - |
| `--verbose` / `-v` | 顯示逐檔解析進度 | - |
| `--list` | 列出所有發現的函式，然後結束 | - |

---

## 使用範例

### 1. 最基本：追蹤一個函式

```bash
tracer my_func src/
```

掃描 `src/` 目錄，追蹤 `my_func`，產生：
- `my_func.puml`
- `my_func_activity.puml`
- `my_func_sequence.puml`

---

### 2. 指定追蹤深度

```bash
tracer process_request . --depth 3
```

只往上 / 往下追蹤 3 層，避免圖表過大。

---

### 3. 使用限定名稱消除歧義

```bash
tracer MyClass.my_method src/ --depth 3
```

當多個類別都有 `my_method` 時，用 `ClassName.method` 精確指定。

---

### 4. 指定輸出路徑

```bash
tracer process_request . --output docs/diagrams/process_request.puml
```

三個圖表將輸出為：
- `docs/diagrams/process_request.puml`
- `docs/diagrams/process_request_activity.puml`
- `docs/diagrams/process_request_sequence.puml`

---

### 5. 不知道函式名稱？先列出全部

```bash
tracer placeholder . --list
```

輸出所有被發現的函式及其所在檔案與行號，再決定要追蹤哪一個。

---

### 6. 跨語言追蹤

```bash
tracer foo file_a.py file_b.js --verbose
```

同時掃描 Python 和 JavaScript 檔案，`--verbose` 顯示每個檔案的解析結果。

---

### 7. 只要 Call Graph，不要其他圖

```bash
tracer my_func src/ --no-activity --no-sequence
```

---

### 8. Sequence diagram 顯示更多層呼叫者

```bash
tracer my_func src/ --seq-depth 8
```

---

## 三種圖表說明

### Call Graph（`.puml`）

```
[ Callers - depth 2 ]  [ Callers - depth 1 ]  [ TARGET ]  [ Callees - depth 1 ]  [ Callees - depth 2 ]
```

- 左側：呼叫目標函式的函式（按深度分群）
- 中央：目標函式（深藍色高亮）
- 右側：目標函式呼叫的函式（按深度分群）
- 箭頭標籤：`[N]` = 呼叫順序, `dN` = 深度

**節點顏色（依語言）：**
- 藍色：Python
- 綠色：JavaScript / TypeScript
- 黃色：Java
- 紅色：C / C++

---

### Activity Diagram（`_activity.puml`）

顯示函式**內部邏輯流程**（目前支援 Python，其他語言顯示呼叫列表）：

| 程式碼 | PlantUML 呈現 |
|--------|--------------|
| `if condition:` | 菱形決策節點 |
| `elif condition:` | elseif 分支 |
| `else:` | else 分支 |
| `for x in items:` | while 迴圈（for x in items?） |
| `while condition:` | while 迴圈（condition?） |
| `try / except / finally` | partition 區塊 |
| `return value` | 綠色終止節點 |
| `raise Exception` | 紅色終止節點 |
| `foo(args)` | 藍色動作節點 |
| `x = value` | 灰色賦值節點 |
| `break` | 橘色節點 |
| `continue` | 紫色節點 |
| `assert cond` | 菱形 + fail 分支 |
| `match/case` (Python 3.10+) | partition + if/elseif 鏈 |

---

### Sequence Diagram（`_sequence.puml`）

顯示**雙向 sequence flow**（往上呼叫者鏈 + 往下被呼叫鏈）：

```
[caller depth 2] → [caller depth 1] → [TARGET] → [callee] → [sub-callee]
                                               ← return ←  ← return ←
← return ←        ← return ←
```

- `→` 實線：函式呼叫，標籤格式 `[N] func_name(args)`
- `-->` 虛線：return，標籤 `return`
- `--seq-depth N`：往上顯示幾層 callers（預設 5）
- `--forward-depth N`：往下顯示幾層 callees（預設 3）

---

## 渲染 PlantUML 圖表

```bash
# 使用 plantuml.jar（需要 Java）
java -jar plantuml.jar *.puml

# 產生所有 PNG
java -jar plantuml.jar -tpng *.puml

# 產生 SVG
java -jar plantuml.jar -tsvg *.puml
```

或使用線上編輯器：複製 `.puml` 內容貼到 [https://www.plantuml.com/plantuml/uml/](https://www.plantuml.com/plantuml/uml/)

也可以使用 VS Code 的 PlantUML 擴充套件直接預覽。

---

## 支援語言與副檔名

| 語言 | 副檔名 | Activity 圖完整邏輯 |
|------|--------|---------------------|
| Python | `.py` | ✅ 完整 if/for/while/try/match |
| JavaScript / TypeScript | `.js` `.jsx` `.ts` `.tsx` | 僅呼叫列表 |
| Java | `.java` | 僅呼叫列表 |
| C / C++ | `.c` `.cpp` `.cc` `.cxx` `.h` `.hpp` | ✅ 完整 if/for/while/switch/return（需 `pip install libclang`）|

---

## 程式庫 API 用法

```python
from tracer.cli import build_graph, _collect_source_files
from tracer.analyzer import analyze
from tracer.exporters import PlantUMLExporter, ActivityExporter, SequenceExporter

# 1. 收集原始碼檔案
files = _collect_source_files(["src/"])

# 2. 建立呼叫圖
graph = build_graph(files, verbose=True)

# 3. 追蹤目標函式
results = analyze(graph, "my_func", max_depth=5)

# 4. 匯出三種圖表
cg = PlantUMLExporter()
act = ActivityExporter()
seq = SequenceExporter()

for result in results:
    cg.export_to_file(result, graph, "output.puml")
    seq.export_to_file(result, graph, "output_sequence.puml", max_depth=5)
    # Activity 需要先用 PythonLogicParser 取得 FunctionBody
```

---

## 專案結構

```
tracecode/
├── trace.py                        # 直接執行入口點
├── setup.py                        # 套件安裝設定
├── docs/                           # 文件
│   ├── usage.md                    # 此使用教學
│   └── checklist.md                # 開發 checklist
└── tracer/
    ├── cli.py                      # CLI 主流程
    ├── graph.py                    # CallGraph / FunctionNode 資料結構
    ├── analyzer.py                 # 雙向 BFS 追蹤邏輯
    ├── logic.py                    # 內部邏輯流程資料結構
    ├── parsers/
    │   ├── base_parser.py          # 解析器基底類別
    │   ├── python_parser.py        # Python 呼叫圖解析器
    │   ├── python_logic_parser.py  # Python 內部邏輯解析器（AST）
    │   ├── javascript_parser.py    # JS/TS 解析器
    │   ├── java_parser.py          # Java 解析器
    │   └── c_parser.py             # C/C++ 解析器
    └── exporters/
        ├── plantuml_exporter.py    # Call Graph 匯出
        ├── activity_exporter.py    # Activity 圖匯出
        └── sequence_exporter.py    # Sequence 圖匯出
```
