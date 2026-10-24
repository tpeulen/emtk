cmake_minimum_required(VERSION 3.20)
project(cpp_hello LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_subdirectory(../.. emtk_build EXCLUDE_FROM_ALL)

add_executable(cpp_hello main.cpp)
target_link_libraries(cpp_hello PRIVATE emtk)
