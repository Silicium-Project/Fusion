#include <stdio.h>

int main(void) {
    char buf[128];
    if (!fgets(buf, sizeof(buf), stdin)) {
        puts("(no input)");
        return 0;
    }
    printf("User typed: %s", buf);
    return 0;
}
