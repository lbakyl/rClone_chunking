Purpose: This script uses rclone to copy over files from
source to destination. Files that are larger than a pre-defined
value are chunked into pieces and rcloned individually.

Requirements: Python 3.x, Rclone (already set up via rclone config)
Tested on: Win 10, Mac OS (15.x - Catalina) and Linux (Synology DSM)

Usage: Use on your NAS or other system to backup data to
a cloud-based service that has a limitation of max file
size, such as Box. Chunk files are stored on the source under .rclone folder.
This means that extra space is required on the NAS to store the chunks.

Features: Max file size can be changed even when large files
have already been chunked. Every time the script runs, every
file and chunk file is verified for integrity and a match with
the user-defined chunk size. If the verification fails
then the chunks are deleted (on source + destination) and
new chunks are created from the original large file.