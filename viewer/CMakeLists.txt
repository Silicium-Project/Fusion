cmake_minimum_required(VERSION 3.16)
project(fragment_viewer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 COMPONENTS Widgets QUIET)
if (Qt6_FOUND)
    set(QT_LIBS Qt6::Widgets)
else()
    find_package(Qt5 COMPONENTS Widgets REQUIRED)
    set(QT_LIBS Qt5::Widgets)
endif()

add_executable(fragment_viewer
    src/main.cpp
    src/GraphModel.cpp
    src/GraphWindow.cpp
)

target_include_directories(fragment_viewer PRIVATE src)
target_link_libraries(fragment_viewer PRIVATE ${QT_LIBS})

set(VIEWER_TS_FILES
    ${CMAKE_CURRENT_SOURCE_DIR}/translations/fragment_viewer_fr_FR.ts
)

find_program(QT_LUPDATE_EXECUTABLE NAMES lupdate-qt6 lupdate6 lupdate)
find_program(QT_LRELEASE_EXECUTABLE NAMES lrelease-qt6 lrelease6 lrelease)

if (QT_LUPDATE_EXECUTABLE AND QT_LRELEASE_EXECUTABLE)
    add_custom_target(fragment_viewer_lupdate
        COMMAND ${QT_LUPDATE_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR} -ts ${VIEWER_TS_FILES}
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        COMMENT "Updating Qt translation sources"
    )

    set(VIEWER_QM_DIR ${CMAKE_CURRENT_BINARY_DIR}/translations)
    file(MAKE_DIRECTORY ${VIEWER_QM_DIR})

    set(VIEWER_QM_FILES "")
    foreach(ts_file IN LISTS VIEWER_TS_FILES)
        get_filename_component(ts_base ${ts_file} NAME_WE)
        set(qm_file ${VIEWER_QM_DIR}/${ts_base}.qm)
        list(APPEND VIEWER_QM_FILES ${qm_file})

        add_custom_command(
            OUTPUT ${qm_file}
            COMMAND ${QT_LRELEASE_EXECUTABLE} ${ts_file} -qm ${qm_file}
            DEPENDS ${ts_file}
            WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
            COMMENT "Compiling ${ts_base}.ts -> ${ts_base}.qm"
        )
    endforeach()

    add_custom_target(fragment_viewer_translations DEPENDS ${VIEWER_QM_FILES})
    add_dependencies(fragment_viewer fragment_viewer_translations)

    add_custom_command(TARGET fragment_viewer POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:fragment_viewer>/translations"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different ${VIEWER_QM_FILES} "$<TARGET_FILE_DIR:fragment_viewer>/translations"
        COMMENT "Copying translations next to fragment_viewer"
        VERBATIM
    )
endif()
