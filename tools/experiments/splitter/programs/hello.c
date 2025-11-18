#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <SFML/Graphics.h>

int main(void) {
    sfVideoMode mode = {800, 600, 32};
    sfRenderWindow *window =
        sfRenderWindow_create(mode, "Hello CSFML", sfResize | sfClose, NULL);
    if (!window) {
        fprintf(stderr, "Failed to create window\n");
        return 1;
    }

    for (int i = 0; i < 10; ++i) {
        double result = sqrt(i * 10.0);
        printf("Sqrt of %d is %.2f\n", i * 10, result);
    }

    sfEvent event;
    while (sfRenderWindow_isOpen(window)) {
        while (sfRenderWindow_pollEvent(window, &event)) {
            if (event.type == sfEvtClosed)
                sfRenderWindow_close(window);
        }
        sfRenderWindow_clear(window, sfBlack);
        sfRenderWindow_display(window);
        break; /* keep the sample short */
    }

    sfRenderWindow_destroy(window);
    return 0;
}
