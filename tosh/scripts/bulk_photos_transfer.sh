#!/bin/bash
# Bulk transfer photos to server

SOURCE_DIR="$HOME/Pictures/Photos Library.photoslibrary/originals/"
DEST="rhea-dev:/home/dshanklin/data/photos/originals/"

echo "Starting bulk photo transfer..."
echo "Source: $SOURCE_DIR"
echo "Destination: $DEST"
echo "This may take several hours for 110GB..."

rsync -avz --progress "$SOURCE_DIR" "$DEST"

echo "Transfer complete!"
