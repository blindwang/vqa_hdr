# minimum required cmake version
cmake_minimum_required( VERSION 3.5 FATAL_ERROR )

# project name
project( HDRTools )

# set default CMAKE_BUILD_TYPE to Release if not set
if( NOT CMAKE_BUILD_TYPE )
  set ( CMAKE_BUILD_TYPE "Release" CACHE STRING "Choose the type of build, options are: Debug Release." FORCE )
endif()

#set c++11
set( CMAKE_CXX_STANDARD 11 )
set( CMAKE_CXX_STANDARD_REQUIRED ON )

# Put binaries/libs in bin/lib directory
if(BINARIES_IN_SOURCETREE)
  set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/lib)
  set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/bin)
  set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/lib)
else()
  set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
  set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
  set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
endif()

# use folders in IDEs for projects
set_property( GLOBAL PROPERTY USE_FOLDERS ON )

# compile everything position independent (even static libraries)
set( CMAKE_POSITION_INDEPENDENT_CODE TRUE )

if( CMAKE_COMPILER_IS_GNUCC )
  set( BUILD_STATIC OFF CACHE BOOL "Build static executables" )
endif()

option(LIBPNG "Use the official libpng repository to read/write .png files" OFF)
option(LIBJPEG "Use the libjpeg-turbo repository to read JPEG files" OFF)

if(LIBPNG OR LIBJPEG)
  # get dependencies
  find_package(Git QUIET)
  if(GIT_FOUND AND EXISTS "${PROJECT_SOURCE_DIR}/.git")
    # Update submodules as needed
    option(GIT_SUBMODULE "Check submodules during build" ON)
    if(GIT_SUBMODULE)
      message(STATUS "Update submodules")
      execute_process(COMMAND ${GIT_EXECUTABLE} submodule update --init
                      WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
                      RESULT_VARIABLE GIT_SUBMOD_RESULT)
      if(NOT GIT_SUBMOD_RESULT EQUAL "0")
        message(FATAL_ERROR "git submodule update --init failed with ${GIT_SUBMOD_RESULT}, please checkout submodules")
      endif()
    endif()
  endif()
endif()

if(LIBPNG)
  # check if we are good with LIBPNG
  if( NOT EXISTS "${PROJECT_SOURCE_DIR}/libs/libpng/CMakeLists.txt")
    message(FATAL_ERROR "The submodules were not downloaded! GIT_SUBMODULE was turned off or failed. Please update submodules and try again.")
  endif()

  # check if we are ok on the zlib front
  find_package(ZLIB QUIET)
  if ( NOT ZLIB_FOUND )
    message("zlib was not fond on your system. Build from source.")
    set(SKIP_INSTALL_ALL ON)
    add_subdirectory("libs/zlib")
    set(PNG_TESTS OFF CACHE BOOL "Build libpng tests" FORCE)
    set(PNG_BUILD_ZLIB ON CACHE BOOL "ZLIB is already build or package is found" FORCE)
    set(ZLIB_INCLUDE_DIRS "${CMAKE_CURRENT_SOURCE_DIR}/libs/zlib/" "${CMAKE_CURRENT_BINARY_DIR}/libs/zlib" CACHE INTERNAL "")
    set(ZLIB_LIBRARIES zlibstatic)    
  endif()

  add_compile_definitions(LIBPNG)
  add_subdirectory("libs/libpng")
endif()

if(LIBJPEG)
  # check if we are good with LIBJPEG
  if( NOT EXISTS "${PROJECT_SOURCE_DIR}/libs/libjpeg-turbo/CMakeLists.txt")
    message(FATAL_ERROR "The submodules were not downloaded! GIT_SUBMODULE was turned off or failed. Please update submodules and try again.")
  endif()

  set(ENABLE_SHARED FALSE CACHE BOOL "Build libpng tests" FORCE)
  add_compile_definitions(LIBJPEG)
  set(CMAKE_INSTALL_DOCDIR "doc") # this is a hack to make libjpeg-turbo compile
  add_subdirectory("libs/libjpeg-turbo")
endif()

if(WIN32)
  set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /fp:strict")
ENDIF()

# add needed subdirectories
add_subdirectory( "common" )
add_subdirectory( "projects/ChromaConvert" )
add_subdirectory( "projects/GamutTest" )
add_subdirectory( "projects/HDRConvert" )
add_subdirectory( "projects/HDRConvScaler" )
add_subdirectory( "projects/HDRMetrics" )
add_subdirectory( "projects/HDRMontage" )
add_subdirectory( "projects/HDRVQM" )
