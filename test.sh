#!/bin/bash
# Test script to classify all supported files in .testfiles directory

API_URL="${API_URL:-http://localhost:8080}"
THRESHOLD="${THRESHOLD:-0.35}"
TEST_DIR=".testfiles"

# Check if test directory exists and has files
if [[ ! -d "$TEST_DIR" ]]; then
    echo "Error: $TEST_DIR directory not found" >&2
    exit 1
fi

# Supported extensions
EXTENSIONS="jpg|jpeg|png|webp|gif|bmp|mp4|webm|avi|mov|mkv|pdf|docx|pptx"

# Count supported files
FILE_COUNT=$(find "$TEST_DIR" -type f -regextype posix-extended -iregex ".*\.($EXTENSIONS)$" 2>/dev/null | wc -l)

if [[ "$FILE_COUNT" -eq 0 ]]; then
    echo "No supported files found in $TEST_DIR"
    echo "Supported: images (jpg, png, webp, gif, bmp), videos (mp4, webm, avi, mov, mkv), pdf, docx, pptx"
    exit 0
fi

echo "Testing $FILE_COUNT files from $TEST_DIR"
echo "API: $API_URL | Threshold: $THRESHOLD"
echo "----------------------------------------"

UNSAFE_COUNT=0
SAFE_COUNT=0
ERROR_COUNT=0

for file in "$TEST_DIR"/*; do
    # Skip unsupported files
    if [[ ! "$file" =~ \.($EXTENSIONS)$ ]]; then
        continue
    fi

    filename=$(basename "$file")
    
    # Call the classify endpoint. An error answer (too large, over a media
    # limit, at capacity, timed out) fails like a lost connection does, and
    # keeps its body for the message.
    if ! response=$(curl -sS --fail-with-body -F "file=@$file" "$API_URL/classify?threshold=$THRESHOLD" 2>&1); then
        echo "[$filename] ERROR: ${response//$'\n'/ }" >&2
        ((ERROR_COUNT++))
        continue
    fi

    # Parse response
    unsafe=$(echo "$response" | grep -o '"unsafe":[^,]*' | cut -d':' -f2)
    confidence=$(echo "$response" | grep -o '"confidence":[^,]*' | cut -d':' -f2)
    classes=$(echo "$response" | grep -o '"detected_classes":\[[^]]*\]' | sed 's/"detected_classes"://')

    if [[ "$unsafe" == "true" ]]; then
        echo "[$filename] UNSAFE (confidence: $confidence) $classes"
        ((UNSAFE_COUNT++))
    elif [[ "$unsafe" == "false" ]]; then
        echo "[$filename] SAFE"
        ((SAFE_COUNT++))
    else
        echo "[$filename] ERROR: no verdict in $response" >&2
        ((ERROR_COUNT++))
    fi
done

echo "----------------------------------------"
echo "Results: $SAFE_COUNT safe, $UNSAFE_COUNT unsafe, $ERROR_COUNT errors"
