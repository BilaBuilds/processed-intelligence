#!/usr/bin/env bash
# ClawShield - security scanner for regulation alert content
# Usage:
#   echo "text" | bash clawshield.sh scan
#   echo "text" | bash clawshield.sh sanitize
#   bash clawshield.sh check-url "https://..."
#
# Output contract:
#   STATUS=ok|review|blocked
#   RISK=low|medium|high
#   MATCHES=<int>
#   CATEGORIES=<comma-separated>

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATTERNS_DIR="$SCRIPT_DIR/patterns"

# All categories trigger STATUS=blocked (fail closed)
HIGH_SEVERITY_CATS="prompt_injection command_injection ssrf credential_theft path_traversal"

# Scan text (passed as a file path) against a pattern file.
# Echoes the count of matches.
_count_matches() {
    local pattern_file="$1"
    local text_file="$2"
    local count=0
    if [[ ! -f "$pattern_file" ]]; then
        echo 0
        return
    fi
    # Build a patterns-only temp file (strip comments and blanks)
    local tmp_patterns
    tmp_patterns=$(mktemp)
    grep -v '^#' "$pattern_file" | grep -v '^[[:space:]]*$' > "$tmp_patterns" || true
    if [[ -s "$tmp_patterns" ]]; then
        count=$(grep -ciEf "$tmp_patterns" "$text_file" 2>/dev/null) || count=0
    fi
    rm -f "$tmp_patterns"
    echo "$count"
}

scan_input() {
    local input_text="$1"

    # Write input to a temp file so grep can search it
    local tmp_input
    tmp_input=$(mktemp)
    printf '%s' "$input_text" > "$tmp_input"

    local total_matches=0
    local matched_categories=()

    local categories=(
        "prompt_injection"
        "command_injection"
        "ssrf"
        "credential_theft"
        "path_traversal"
    )

    for category in "${categories[@]}"; do
        local pattern_file="$PATTERNS_DIR/${category}.txt"
        local count
        count=$(_count_matches "$pattern_file" "$tmp_input")
        if [[ "$count" -gt 0 ]]; then
            matched_categories+=("$category")
            total_matches=$((total_matches + count))
        fi
    done

    rm -f "$tmp_input"

    local status="ok"
    local risk="low"
    local categories_str=""

    if [[ ${#matched_categories[@]} -gt 0 ]]; then
        categories_str=$(IFS=','; echo "${matched_categories[*]}")
        local is_blocked=0
        for cat in "${matched_categories[@]}"; do
            for high_cat in $HIGH_SEVERITY_CATS; do
                if [[ "$cat" == "$high_cat" ]]; then
                    is_blocked=1
                    break 2
                fi
            done
        done
        if [[ "$is_blocked" -eq 1 ]]; then
            status="blocked"
            risk="high"
        else
            status="review"
            risk="medium"
        fi
    fi

    echo "STATUS=$status"
    echo "RISK=$risk"
    echo "MATCHES=$total_matches"
    echo "CATEGORIES=${categories_str:-none}"

    if [[ "$status" == "blocked" ]]; then
        exit 1
    fi
    exit 0
}

do_scan() {
    local input_file="${1:-}"
    local input_text

    if [[ -n "$input_file" && -f "$input_file" ]]; then
        input_text=$(cat "$input_file")
    elif [[ ! -t 0 ]]; then
        input_text=$(cat)
    else
        echo "STATUS=error" >&2
        echo "RISK=high" >&2
        echo "MATCHES=0" >&2
        echo "CATEGORIES=none" >&2
        exit 1
    fi

    scan_input "$input_text"
}

do_sanitize() {
    local input_text
    if [[ ! -t 0 ]]; then
        input_text=$(cat)
    else
        echo "STATUS=error" >&2
        exit 1
    fi

    # Check for blocked content first - capture output without triggering exit
    local tmp_input
    tmp_input=$(mktemp)
    printf '%s' "$input_text" > "$tmp_input"

    local scan_status="ok"
    local total_matches=0
    local high_severity_found=0

    local categories=(
        "prompt_injection"
        "command_injection"
        "ssrf"
        "credential_theft"
        "path_traversal"
    )

    for category in "${categories[@]}"; do
        local pattern_file="$PATTERNS_DIR/${category}.txt"
        local count
        count=$(_count_matches "$pattern_file" "$tmp_input")
        if [[ "$count" -gt 0 ]]; then
            total_matches=$((total_matches + count))
            for high_cat in $HIGH_SEVERITY_CATS; do
                if [[ "$category" == "$high_cat" ]]; then
                    high_severity_found=1
                    break
                fi
            done
        fi
    done

    rm -f "$tmp_input"

    if [[ "$high_severity_found" -eq 1 ]]; then
        echo "STATUS=blocked"
        echo "RISK=high"
        echo "MATCHES=$total_matches"
        echo "CATEGORIES=blocked_content"
        exit 1
    fi

    # Strip dangerous shell metacharacters without mutating semantic meaning
    local sanitized
    sanitized=$(echo "$input_text" | \
        sed 's/`[^`]*`//g' | \
        sed 's/\$([^)]*)/\$REDACTED/g' | \
        sed 's/[;|&][[:space:]]*\(rm\|wget\|curl\|bash\|sh\|python\|perl\|nc\|netcat\)//gi')

    echo "$sanitized"
    echo "STATUS=ok" >&2
    exit 0
}

do_check_url() {
    local url="${1:-}"
    if [[ -z "$url" ]]; then
        echo "STATUS=error"
        echo "RISK=high"
        echo "MATCHES=0"
        echo "CATEGORIES=none"
        exit 1
    fi

    # Extract host from URL
    local host
    host=$(echo "$url" | sed 's|^[a-zA-Z]*://||' | sed 's|/.*||' | sed 's|:.*||')

    # Block non-http schemes
    case "$url" in
        file://*|gopher://*|dict://*)
            echo "STATUS=blocked"
            echo "RISK=high"
            echo "MATCHES=1"
            echo "CATEGORIES=ssrf"
            exit 1
            ;;
    esac

    local blocked_patterns=(
        "^localhost$"
        "^127\."
        "^0\.0\.0\.0"
        "^::1$"
        "^169\.254\."
        "^metadata\.google\.internal$"
        "^192\.168\."
        "^10\."
        "^172\.(1[6-9]|2[0-9]|3[01])\."
    )

    for pattern in "${blocked_patterns[@]}"; do
        if echo "$host" | grep -qE "$pattern"; then
            echo "STATUS=blocked"
            echo "RISK=high"
            echo "MATCHES=1"
            echo "CATEGORIES=ssrf"
            exit 1
        fi
    done

    echo "STATUS=ok"
    echo "RISK=low"
    echo "MATCHES=0"
    echo "CATEGORIES=none"
    exit 0
}

CMD="${1:-}"
case "$CMD" in
    scan)
        shift
        do_scan "${1:-}"
        ;;
    sanitize)
        do_sanitize
        ;;
    check-url)
        shift
        do_check_url "${1:-}"
        ;;
    *)
        echo "Usage: clawshield.sh <scan|sanitize|check-url> [args]" >&2
        exit 1
        ;;
esac
