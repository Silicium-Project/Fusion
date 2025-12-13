#include <fstream>
#include <iostream>
#include <string>

// Exemple pour montrer la dépendance aux stubs CRT : le fichier est ouvert
// dans la séquence .init_array avant main. Si on saute _start/_init et qu'on
// appelle main directement, log_file n'est pas initialisé et l'écriture échoue.
std::ofstream log_file("ctor_demo.log");

int main() {
    if (!log_file.is_open()) {
        std::cerr << "log_file non initialisé\n";
        return 1;
    }
    log_file << "Hello from ctor demo\n";
    log_file.flush();
    std::cout << "Écriture terminée, vérifiez ctor_demo.log\n";
    return 0;
}
