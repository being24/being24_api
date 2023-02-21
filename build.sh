#!/bin/bash
cd `dirname $0`
docker build ./docker/ -t ayame_fastapi
