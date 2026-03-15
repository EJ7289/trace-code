# call-tracer

跨語言雙向函式呼叫圖追蹤工具，並可匯出 PlantUML 圖表。

## 功能概覽

- **雙向追蹤**：從任一目標函式出發，同時找出所有呼叫者（backward）與所有被呼叫者（forward）
- **跨語言支援**：Python、JavaScript/TypeScript、Java、C/C++
- **遞迴掃描**：可指定整個目錄，自動遞迴掃描所有支援的原始碼檔案
- **PlantUML 匯出**：自動產生 `.puml` 圖表，節點依語言著色

## 系統需求

- Python 3.8 以上

## 安裝

```bash
pip install -e .
```

安裝後即可使用 `tracer` 命令。也可直接透過 `python trace.py` 執行（不需安裝）。

## 支援的語言與副檔名

| 語言             | 副檔名                              |
|------------------|-------------------------------------|
| Python           | `.py`                               |
| JavaScript / TS  | `.js` `.jsx` `.ts` `.tsx`           |
| Java             | `.java`                             |
| C / C++          | `.c` `.cpp` `.cc` `.cxx` `.h` `.hpp`|

## 基本用法

```
tracer <目標函式名稱> <路徑 [路徑 ...]> [選項]
```

或不安裝直接執行：

```
python trace.py <目標函式名稱> <路徑 [路徑 ...]> [選項]
```

### 參數說明

| 參數 | 說明 |
|------|------|
| `function` | 目標函式名稱，可用簡單名稱（`foo`）或限定名稱（`MyClass.foo`） |
| `PATH ...` | 要掃描的原始碼檔案或目錄（目錄會遞迴掃描） |
| `--depth N` / `-d N` | 最大追蹤深度（預設：不限） |
| `--output FILE` / `-o FILE` | 輸出 `.puml` 的檔案路徑（預設：`<函式名稱>.puml`） |
| `--no-files` | 圖表節點不顯示檔案與行號資訊 |
| `--verbose` / `-v` | 顯示逐檔解析進度 |
| `--list` | 列出所有被發現的函式，而不進行追蹤 |

## 使用範例

### 1. 追蹤單一函式

```bash
tracer my_func src/
```

掃描 `src/` 目錄下所有支援的原始碼，追蹤 `my_func` 的呼叫關係。

### 2. 追蹤方法（限定名稱）

```bash
tracer MyClass.my_method src/ --depth 3
```

追蹤 `MyClass` 的 `my_method`，最多往上／往下追蹤 3 層。

### 3. 指定輸出檔案

```bash
tracer process_request . --output call_graph.puml
```

掃描當前目錄，結果輸出到 `call_graph.puml`。

### 4. 掃描多個路徑

```bash
tracer foo file_a.py file_b.js --verbose
```

同時掃描兩個特定檔案，並顯示解析進度。

### 5. 先列出所有函式再決定追蹤目標

```bash
tracer placeholder . --list
```

列出所有被發現的函式（第一個參數在 `--list` 模式下被忽略）。

## 輸出說明

### 終端機輸出

執行追蹤後，終端機會顯示：

```
Target : MyClass.process
  File : src/handler.py:42
  Lang : python
  Backward (callers) : 3 function(s)
  * main           ← 直接呼叫者（標有 *）
    router.dispatch
    middleware.run
  Forward  (callees) : 2 function(s)
  * db.query       ← 直接被呼叫者（標有 *）
    logger.info
```

- `*` 標記代表深度為 1 的直接呼叫關係
- 未標記的表示間接（遞移）呼叫關係

### PlantUML 圖表

產生的 `.puml` 檔包含：

- **左側群組（Callers / Backward）**：所有呼叫目標函式的函式
- **中央（Target）**：目標函式（深藍色高亮）
- **右側群組（Callees / Forward）**：目標函式所呼叫的所有函式
- **節點顏色**依語言區分：
  - 藍色：Python
  - 綠色：JavaScript / TypeScript
  - 黃色：Java
  - 紅色：C / C++

可使用 [PlantUML](https://plantuml.com/) 工具（命令列、IDE 外掛、線上編輯器）將 `.puml` 轉成 PNG / SVG 圖片。

```bash
# 使用 plantuml.jar 產生圖片
java -jar plantuml.jar my_func.puml
```

## 同名函式（歧義處理）

若程式碼中存在多個同名函式（例如不同類別各有一個 `save` 方法），工具會對**每一個**符合的函式分別產生一份追蹤結果與圖表。

建議使用限定名稱（`ClassName.method`）來精確指定目標，避免歧義。

## 程式庫 API

除了命令列外，也可在 Python 程式碼中直接使用：

```python
from tracer.cli import build_graph, _collect_source_files
from tracer.analyzer import analyze
from tracer.exporters import PlantUMLExporter

# 1. 收集原始碼檔案
files = _collect_source_files(["src/"])

# 2. 建立呼叫圖
graph = build_graph(files, verbose=True)

# 3. 追蹤目標函式
results = analyze(graph, "my_func", max_depth=5)

# 4. 匯出 PlantUML
exporter = PlantUMLExporter()
for result in results:
    exporter.export_to_file(result, graph, "output.puml", show_files=True)
```

## 專案結構

```
tracecode/
├── trace.py                  # 直接執行的入口點
├── setup.py                  # 套件安裝設定
└── tracer/
    ├── cli.py                # 命令列介面與主流程
    ├── graph.py              # CallGraph / FunctionNode 資料結構
    ├── analyzer.py           # 雙向 BFS 追蹤邏輯
    ├── parsers/
    │   ├── base_parser.py    # 解析器基底類別
    │   ├── python_parser.py  # Python 解析器
    │   ├── javascript_parser.py  # JS/TS 解析器
    │   ├── java_parser.py    # Java 解析器
    │   └── c_parser.py       # C/C++ 解析器
    └── exporters/
        └── plantuml_exporter.py  # PlantUML 圖表匯出器
```
