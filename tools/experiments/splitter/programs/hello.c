#include <stdio.h>
#include <stdlib.h>

int main(int argc, char *argv[]) {
    int n = 1;
    char **arr = (char **)malloc(n * sizeof(char *));
    for (int i = 0; i < n; i++) {
        arr[i] = argv[i];
    }
    for (int i = 0; i < n; i++) {
        printf("%s\n", arr[i]);
    }
    free(arr);
    return 0;
}