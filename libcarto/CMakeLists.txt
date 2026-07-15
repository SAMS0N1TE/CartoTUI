cmake_minimum_required(VERSION 3.16)
project(carto C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

option(CARTO_BUILD_TESTS "Build the render harnesses" ON)
option(CARTO_WERROR "Treat warnings as errors" OFF)

set(CARTO_SOURCES
    src/style.c
    src/framebuffer.c
    src/raster.c
    src/geom.c
    src/mvt.c
    src/carto.c
)

add_library(carto SHARED ${CARTO_SOURCES})
set_target_properties(carto PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(carto PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)

if(CARTO_WERROR)
    target_compile_options(carto PRIVATE -Wall -Wextra -Werror)
else()
    target_compile_options(carto PRIVATE -Wall -Wextra)
endif()

find_library(CARTO_M m)
if(NOT CARTO_M)
    set(CARTO_M "")
endif()

if(CARTO_BUILD_TESTS)
    if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/tests/render_to_bmp.c)
        add_executable(render_to_bmp tests/render_to_bmp.c)
        target_link_libraries(render_to_bmp PRIVATE carto ${CARTO_M})
    endif()
    if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/tests/render_tile_to_bmp.c)
        add_executable(render_tile_to_bmp tests/render_tile_to_bmp.c)
        target_link_libraries(render_tile_to_bmp PRIVATE carto ${CARTO_M})
    endif()
endif()
