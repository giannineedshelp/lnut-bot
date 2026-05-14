#!/data/data/com.termux/files/usr/bin/bash

pkg update -y && pkg upgrade -y
pkg install git python openssh -y

termux-setup-storage

mkdir -p /storage/emulated/0/Documents

cd /storage/emulated/0/Documents

git clone git@github.com:giannineedshelp/lnut-bot.git

cd lnut-bot/In_bot

pip install -r requirements.txt

echo "Setup complete. Run with: bash run.sh"
