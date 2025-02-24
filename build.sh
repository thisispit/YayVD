#!/bin/bash

# Update package lists
apt-get update

# Install ffmpeg without prompting
DEBIAN_FRONTEND=noninteractive apt-get install -y ffmpeg