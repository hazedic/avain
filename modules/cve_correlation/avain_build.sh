#!/bin/bash

# configure submodules of SQLiteCpp
cd "db_creation_src/SQLiteCpp"
if [ $QUIET != 1 ]; then
    git submodule init
    git submodule update
else
    git submodule --quiet init
    git submodule --quiet update
fi
cd ".."

# get C++ JSON parser from https://github.com/nlohmann/json
mkdir -p "json/single_include/nlohmann"
cd json/single_include/nlohmann
if [ $QUIET != 1 ]; then
    wget https://raw.githubusercontent.com/nlohmann/json/develop/single_include/nlohmann/json.hpp -O json.hpp
else
    wget https://raw.githubusercontent.com/nlohmann/json/develop/single_include/nlohmann/json.hpp -q -O json.hpp
fi
cd "../../../"

rm -rf build
mkdir -p build
cd "build"
if [ $QUIET != 1 ]; then
    cmake ..
    make
else
    cmake --quiet ..
    make --quiet
fi
cp create_db ../../

cd "../../"
eval "./module_updater.py"

if [ $? != 0 ]; then
    echo -e "${RED}Could not update database"
    exit 1
fi