cmake_minimum_required(VERSION 3.20)
project(emtk VERSION 0.1.22 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Provide emtk include directory
add_library(emtk INTERFACE)
target_include_directories(emtk INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

# Find Cargo
find_program(CARGO_BIN cargo HINTS "$ENV{HOME}/.cargo/bin")
if (CARGO_BIN)
    message(STATUS "Found Cargo: ${CARGO_BIN}")
    set(EMTK_LIB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/target/release")
    set(EMTK_STATIC_LIB "${EMTK_LIB_DIR}/libemtk_ffi.a")

    add_custom_target(emtk_ffi_build
        COMMAND ${CARGO_BIN} build --release -p emtk-ffi
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        BYPRODUCTS ${EMTK_STATIC_LIB}
        COMMENT "Compiling emtk-ffi static library via Cargo"
    )

    add_library(emtk_ffi STATIC IMPORTED GLOBAL)
    set_target_properties(emtk_ffi PROPERTIES
        IMPORTED_LOCATION ${EMTK_STATIC_LIB}
    )
    add_dependencies(emtk_ffi emtk_ffi_build)

    if (APPLE)
        target_link_libraries(emtk INTERFACE "-framework Metal -framework AppKit -framework QuartzCore")
    endif()
    target_link_libraries(emtk INTERFACE emtk_ffi)
endif()
