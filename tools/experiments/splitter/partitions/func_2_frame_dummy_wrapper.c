// Wrapper pour partition: func_2_frame_dummy
#include <stdio.h>
#include <stdint.h>

extern void partition_code();

int main() {
    printf("Exécution partition: func_2_frame_dummy\n");
    // partition_code();
    return 0;
}
