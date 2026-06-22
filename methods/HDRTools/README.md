# HDRTools package

This software package is under development to support
video standardization work and may eventually be formally
published as reference software, e.g., by ITU-T and ISO/IEC.

Please do not use this package for any other applications without
the knowledge or permission from the software owners/creators.

## Disclaimer

Please note that this software was developed mainly for research purposes, with
the desire for portability, extensibility, and testing in the context of video
coding standards development. It was highly desirable to make this software
independent from other "non-standard" libraries, such as libraries for I/O and
processing, to ease compilation and testing across multiple platforms. Instead,
such functionality may be replicated in this software, while at the same time,
it may be highly unoptimized or limited in scope. Optimized code, however was
never the intent of this tool. Optimization as well as extensions in scope for
some of this functionality may be added in the future as deemed necessary.

## Build instructions

The Software has CMake support to create platform-specific build files.
A working CMake installation is recommended for building the software.

CMake generates configuration files for the compiler environment/development
environment on each platform. A list of examples is given in the following:

```shell
git clone https://gitlab.com/standards/HDRTools.git
cd HDRTools
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make
```

If you want to select a specific generator use `-G` option e.g.:

Windows Visual Studio 2015 64 Bit:

```shell
cmake .. -G "Visual Studio 14 2015 Win64"
```

macOS Xcode:

```shell
cmake .. -G "Xcode"
```

The binaries are being build in the binary tree. In case you want them to appear
directly in the source tree set `-DBINARIES_IN_SOURCETREE=1`

For more details, refer to the [CMake documentation](https://cmake.org/cmake/help/latest/).

### PNG support

If you want to enable PNG support you can use the `LIBPNG` option which enables [libpng](https://github.com/glennrp/libpng) for your build. Note that [libpng](https://github.com/glennrp/libpng) requires [zlib](https://zlib.net) to be installed on your system.
If `zlib` is not installed on your system, cmake will try to build it from source.

```shell
cmake .. -DLIBPNG=ON
```

### JPEG support

Currenlty only reading basic JPEG images is supported by using the [libjpeg-turbo](https://github.com/libjpeg-turbo/libjpeg-turbo). To enable JPEG you can use the `LIBJPEG` option.

```shell
cmake .. -DLIBJPEG=ON
```

### "All in" build command

```shell
git clone https://gitlab.com/standards/HDRTools.git
cd HDRTools
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DLIBPNG=ON -DLIBJPEG=ON
make -j
```
