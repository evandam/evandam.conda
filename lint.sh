#!/bin/bash

pylint library

if [ $(($? & 3)) -ne 0 ]; then
  echo "Pylint found errors!"
  exit 1
fi