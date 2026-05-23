#!/usr/bin/env bash
# Helper for migrating Apple Reminders to Life Ops todos.
#
# Apple Reminders is exposed via AppleScript. This script dumps a list to
# stdout as TSV (title<TAB>notes<TAB>due<TAB>priority) so you can pipe it
# into your preferred ETL or hand-curate before the MCP server imports it.
set -euo pipefail

LIST="${1:-}"
if [ -z "$LIST" ]; then
  echo "usage: $0 <list-name>"
  echo
  echo "available lists:"
  osascript -e 'tell application "Reminders" to get name of every list' \
    | tr ',' '\n' | sed 's/^ //'
  exit 1
fi

osascript <<EOF
on cleanup(s)
  set s to s as string
  set AppleScript's text item delimiters to {tab, return, linefeed}
  set parts to text items of s
  set AppleScript's text item delimiters to " "
  set s to parts as string
  set AppleScript's text item delimiters to ""
  return s
end cleanup

tell application "Reminders"
  set theList to list "$LIST"
  set out to ""
  repeat with r in (reminders of theList whose completed is false)
    set t to my cleanup(name of r as string)
    set n to ""
    try
      set n to my cleanup(body of r as string)
    end try
    set d to ""
    try
      set d to (due date of r) as string
    end try
    set p to (priority of r) as string
    set out to out & t & tab & n & tab & d & tab & p & linefeed
  end repeat
  return out
end tell
EOF
