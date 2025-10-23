#!/bin/bash
# Sync MULTI_PROJECT_ARCHITECTURE.md across all NeuroSphere projects
# This script pulls the latest version from GitHub and can push updates back

ARCH_FILE="MULTI_PROJECT_ARCHITECTURE.md"
GITHUB_RAW_URL="https://raw.githubusercontent.com/trpl333/ChatStack/main/MULTI_PROJECT_ARCHITECTURE.md"
GITHUB_REPO_URL="https://github.com/trpl333/ChatStack"

echo "🔄 NeuroSphere Architecture Sync Tool"
echo "======================================"

# Function to pull latest from GitHub
pull_latest() {
    echo ""
    echo "📥 Pulling latest architecture from GitHub..."
    
    # Backup current file if it exists
    if [ -f "$ARCH_FILE" ]; then
        cp "$ARCH_FILE" "${ARCH_FILE}.backup"
        echo "   ✓ Backed up current file to ${ARCH_FILE}.backup"
    fi
    
    # Download latest from GitHub
    curl -s "$GITHUB_RAW_URL" -o "$ARCH_FILE"
    
    if [ $? -eq 0 ]; then
        # Extract version from file
        VERSION=$(grep "^**Version:**" "$ARCH_FILE" | head -1 | sed 's/.*Version:\*\* //')
        echo "   ✓ Downloaded version: $VERSION"
        echo "   ✓ File saved to: $ARCH_FILE"
        
        # Show diff if backup exists
        if [ -f "${ARCH_FILE}.backup" ]; then
            if ! diff -q "$ARCH_FILE" "${ARCH_FILE}.backup" > /dev/null; then
                echo ""
                echo "📝 Changes detected:"
                diff "${ARCH_FILE}.backup" "$ARCH_FILE" | head -20
            else
                echo "   ✓ No changes from previous version"
            fi
        fi
    else
        echo "   ✗ Failed to download from GitHub"
        return 1
    fi
}

# Function to show current version
show_version() {
    if [ -f "$ARCH_FILE" ]; then
        VERSION=$(grep "^**Version:**" "$ARCH_FILE" | head -1 | sed 's/.*Version:\*\* //')
        UPDATED=$(grep "^**Last Updated:**" "$ARCH_FILE" | head -1 | sed 's/.*Updated:\*\* //')
        echo ""
        echo "📄 Current Local Version:"
        echo "   Version: $VERSION"
        echo "   Updated: $UPDATED"
    else
        echo ""
        echo "⚠️  Architecture file not found locally"
        echo "   Run: $0 pull"
    fi
}

# Function to push updates to GitHub (requires git setup)
push_updates() {
    echo ""
    echo "📤 Pushing updates to GitHub..."
    echo "   Note: This requires git to be configured in this repo"
    echo ""
    
    if [ ! -f "$ARCH_FILE" ]; then
        echo "   ✗ Architecture file not found"
        return 1
    fi
    
    # Extract new version
    VERSION=$(grep "^**Version:**" "$ARCH_FILE" | head -1 | sed 's/.*Version:\*\* //')
    
    echo "   Current version: $VERSION"
    echo ""
    read -p "   Update version number? (y/n): " UPDATE_VERSION
    
    if [ "$UPDATE_VERSION" = "y" ]; then
        echo "   Enter new version (e.g., 1.3.0):"
        read NEW_VERSION
        sed -i "s/^\*\*Version:\*\*.*/\*\*Version:\*\* $NEW_VERSION/" "$ARCH_FILE"
        # Update date
        NEW_DATE=$(date +"%B %d, %Y")
        sed -i "s/^\*\*Last Updated:\*\*.*/\*\*Last Updated:\*\* $NEW_DATE/" "$ARCH_FILE"
        echo "   ✓ Updated to version $NEW_VERSION"
    fi
    
    # Git commands
    git add "$ARCH_FILE"
    
    echo ""
    read -p "   Enter commit message (or press Enter for default): " COMMIT_MSG
    if [ -z "$COMMIT_MSG" ]; then
        COMMIT_MSG="Updated architecture documentation"
    fi
    
    git commit -m "$COMMIT_MSG"
    git push origin main
    
    echo ""
    echo "   ✓ Pushed to GitHub"
    echo "   ✓ Other Replits can now run: ./sync_architecture.sh pull"
}

# Main menu
case "$1" in
    pull)
        pull_latest
        ;;
    push)
        push_updates
        ;;
    version)
        show_version
        ;;
    *)
        echo ""
        echo "Usage: $0 {pull|push|version}"
        echo ""
        echo "Commands:"
        echo "  pull     - Download latest architecture from GitHub"
        echo "  push     - Upload local changes to GitHub (updates version)"
        echo "  version  - Show current local version"
        echo ""
        echo "Workflow:"
        echo "  1. Before working: ./sync_architecture.sh pull"
        echo "  2. Make changes to your service and update $ARCH_FILE"
        echo "  3. Commit changes: ./sync_architecture.sh push"
        echo "  4. Other Replits will pull your updates"
        echo ""
        echo "GitHub Master: $GITHUB_REPO_URL"
        ;;
esac
