cmake_minimum_required(VERSION 3.15)
project(LocalEvader LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Download WinDivert 2.2 Release
include(FetchContent)

# Provide a local path or download it during build
set(WINDIVERT_URL "https://github.com/basil00/WinDivert/releases/download/v2.2.2/WinDivert-2.2.2-A.zip")

FetchContent_Declare(
    WinDivert
    URL ${WINDIVERT_URL}
)
FetchContent_MakeAvailable(WinDivert)

set(WINDIVERT_DIR ${windivert_SOURCE_DIR})

# Determine architecture to pick correct lib
if(CMAKE_SIZEOF_VOID_P EQUAL 8)
    set(WINDIVERT_LIB_DIR "${WINDIVERT_DIR}/x64")
else()
    set(WINDIVERT_LIB_DIR "${WINDIVERT_DIR}/x86")
endif()

add_executable(Engine src/main.cpp src/Diverter.cpp)

target_include_directories(Engine PRIVATE "${WINDIVERT_DIR}/include")
target_link_libraries(Engine PRIVATE "${WINDIVERT_LIB_DIR}/WinDivert.lib" ws2_32 psapi)

# Copy the DLL and SYS to the executable directory
add_custom_command(TARGET Engine POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
    "${WINDIVERT_LIB_DIR}/WinDivert.dll"
    $<TARGET_FILE_DIR:Engine>
)
if(CMAKE_SIZEOF_VOID_P EQUAL 8)
    add_custom_command(TARGET Engine POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${WINDIVERT_LIB_DIR}/WinDivert64.sys"
        $<TARGET_FILE_DIR:Engine>
    )
else()
    add_custom_command(TARGET Engine POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${WINDIVERT_LIB_DIR}/WinDivert32.sys"
        $<TARGET_FILE_DIR:Engine>
    )
endif()
