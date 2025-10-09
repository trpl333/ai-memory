# 🚀 Manual Production Server Fix - Phone System

## SSH into your server and run these commands:

```bash
ssh root@209.38.143.71
cd /opt/ChatStack
```

## Update main.py (Flask phone handler):

```bash
# Backup original
cp main.py main.py.backup

# Apply the fix
cat > main.py << 'EOF'