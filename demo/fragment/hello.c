#include <stdio.h>
#include <stdint.h>

static int adder(int a, int b) {
    if (a)
        return adder(a - 1, b + 1);
    return b;
}

int main() {
    int x = 5;
    int y = 10;
    int result = adder(x, y);
    printf("Resulttttttttttttttttttttttttttttttttttt: %d\n", result);
    return 0;
}