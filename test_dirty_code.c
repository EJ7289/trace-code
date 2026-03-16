#include <stdio.h>

// 模擬外部硬體或系統介面
extern int sys_read_reg(int addr);
extern void sys_write_reg(int addr, int val);
extern int check_buffer_full();

int ugly_controller_function(int cmd, int len, int *payload) {
    int state = 0;
    int timeout = 100;

    // 1. 混亂的參數檢查與早退
    if (len <= 0) return -1;
    if (payload == NULL) {
        if (cmd != 0xFF) return -2; // 隱含邏輯：只有 0xFF 命令允許空 payload
    }

    // 2. 重複與雜亂的迴圈處理
    for (int i = 0; i < len; i++) {
        // 檢查緩衝區並在中間插入跳出邏輯
        if (check_buffer_full()) {
            printf("Buffer full at index %d\n", i);
            break; 
        }

        // 3. 在迴圈中塞入龐大的判別式
        if (cmd > 10) {
            switch (state) {
                case 0:
                    state = (payload[i] > 0) ? 1 : 2;
                    sys_write_reg(0x10, payload[i]);
                    break;
                case 1:
                    if (payload[i] == 0) {
                        state = 0;
                        continue; // 測試工具是否能畫出返回迴圈頂部的線
                    }
                    sys_write_reg(0x14, payload[i] + state);
                    break;
                default:
                    state = -1;
                    goto ERROR_HANDLER; // 非線性跳轉
            }
        } else {
            // cmd <= 10 的簡單處理
            payload[i] = sys_read_reg(0x20 + i);
        }

        // 4. 內嵌超長超醜的 Timeout 邏輯
        while (timeout > 0) {
            if (sys_read_reg(0x00) == 1) break;
            timeout--;
            if (timeout == 0) return -404; // 巢狀深處的 Return
        }
    }

    // 5. 正常的結尾
    sys_write_reg(0x80, 0x01);
    return state;

ERROR_HANDLER:
    sys_write_reg(0x80, 0xEE);
    return -999;
}