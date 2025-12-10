cmake_minimum_required(VERSION 3.16)
project(fragment_viewer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 COMPONENTS Widgets REQUIRED QUIET)
if (NOT Qt6_FOUND)
    find_package(Qt5 COMPONENTS Widgets REQUIRED)
    set(QT_LIBS Qt5::Widgets)
else()
    set(QT_LIBS Qt6::Widgets)
endif()

add_executable(fragment_viewer
    src/main.cpp
    src/GraphWindow.cpp
)

target_include_directories(fragment_viewer PRIVATE src)
target_link_libraries(fragment_viewer PRIVATE ${QT_LIBS})
