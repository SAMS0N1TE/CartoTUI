set(LIBCARTO_DIR ${CMAKE_CURRENT_LIST_DIR}/../../../../libcarto)

idf_component_register(
    SRCS
        ${LIBCARTO_DIR}/src/style.c
        ${LIBCARTO_DIR}/src/framebuffer.c
        ${LIBCARTO_DIR}/src/raster.c
    INCLUDE_DIRS
        ${LIBCARTO_DIR}/include
)
