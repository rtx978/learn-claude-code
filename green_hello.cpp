#include <iostream>
#include <windows.h>

int main() {
    HANDLE hConsole = GetStdHandle(STD_OUTPUT_HANDLE);
    SetConsoleTextAttribute(hConsole, 0x0A); // 绿色文字
    std::cout << "hi我爱你";
    SetConsoleTextAttribute(hConsole, 0x07); // 恢复默认颜色
    return 0;
}