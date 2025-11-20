#include <stdio.h>
#include <string.h>

int main(void) {
    char buffer[128];

    if (!fgets(buffer, sizeof(buffer), stdin)) {
        fprintf(stderr, "stdin vide\n");
        return 1;
    }

    size_t len = strlen(buffer);
    if (len > 0 && buffer[len - 1] == '\n')
        buffer[len - 1] = '\0';

    printf("Echo stdin: %s\n", buffer);
    return 0;
}
