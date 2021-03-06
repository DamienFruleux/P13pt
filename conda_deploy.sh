#!/bin/bash

for py_ver in 2.7 3.6 3.7
do
    PKG_FILE="$(conda build --python ${py_ver} conda --output)"
    PKG_DIR=$(dirname "${PKG_FILE}")
    CONDA_BLD_DIR=$(dirname "${PKG_DIR}")
    PKG_BASENAME=$(basename "${PKG_FILE}")

    for PLATFORM in linux-32 linux-64 osx-64
    do
        conda convert --platform $PLATFORM $PKG_FILE -o $CONDA_BLD_DIR
        anaconda upload $CONDA_BLD_DIR/$PLATFORM/$PKG_BASENAME
    done

    for PLATFORM in win-32 win-64
    do
        conda convert --platform $PLATFORM --dependencies pywin32 -o $CONDA_BLD_DIR $PKG_FILE
        anaconda upload $CONDA_BLD_DIR/$PLATFORM/$PKG_BASENAME
    done

done