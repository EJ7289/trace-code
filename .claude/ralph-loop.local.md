---
active: true
iteration: 1
session_id: 
max_iterations: 0
completion_promise: null
started_at: "2026-03-15T16:51:59Z"
---


目的：
1. 建立code trace的整個流程，讓我能夠很好的理解整個code的sequance flow

手段：
1. 我給你function name，以及相對應往上即往下trace的層數，你把相對應的整個流程話給我

能夠執行的command
1. grep：去查找整個codebase相對應的function在哪裡

結果：
1. 不用將所有的程式邏輯寫出來，但需要將程式呼叫的 function , 傳遞的參數,回傳的參數都畫在plantuml 中
2. 如果目前的codebase中有多餘的程式碼請幫我刪除
3. 請在./docs底下建立文檔，需要包含：使用教學、checklist(你做了甚麼，每座一步都需要去更新)

