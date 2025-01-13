#!/bin/bash

if [[ $# -ne 2 ]]; then
  echo "Error: You must provide exactly two parameters, which should be valid codexes, such as '154a'."
  echo "Usage: $0 <codex1> <codex2>"
  exit 1
fi

BASEDIR=data/xml
CODEX1=$1
CODEX2=$2
C1DIR=${BASEDIR}/${CODEX1}
C2DIR=${BASEDIR}/${CODEX2}

if [ ! -d $C1DIR ]; then
    echo "Invalid codex: $CODEX1. (Directory $C1DIR not found)."
    exit 1
fi;

if [ ! -d $C2DIR ]; then
    echo "Invalid codex: $CODEX2. (Directory $C2DIR not found)."
    exit 1
fi;

SKIP=("index.xml", "references.xml", "problems.xml")

for a in $(ls -1 $C1DIR); do
    if [[ "${SKIP[@]}" =~ "$a" ]]; then
        continue
    fi
    echo -ne "$a"
    echo -ne "\\033[20G"
    echo -n $a | sed -E 's/^([0-9]{4})\.([0-9md]+)\.xml$/\2\/\1/'
    echo -ne "\\033[40G"
    diff -y --suppress-common-lines ${C1DIR}/${a} ${C2DIR}/${a} | wc -l
done;
