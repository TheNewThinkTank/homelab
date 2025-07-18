# Setup ufw, user and ssh

## Setup ufw

```bash
ubuntu@ubuntu:~/Desktop$ which ufw
/usr/sbin/ufw

ubuntu@ubuntu:~/Desktop$ sudo -i

apt-get update

apt-get install ssh
ufw allow OpenSSH
ufw enable
ufw status
ufw status verbose

sudo apt install nginx
ufw allow 'Nginx Full'
ufw status verbose
```

## Setup user

```bash
adduser "<JohnDoe>"
usermod -aG sudo "<JohnDoe>"
```

## Setup ssh

Get IPv4: `hostname -I`

```bash
sudo nano /etc/ssh/sshd_config
```

Ensure following is set:

```vim
Include /etc/ssh/sshd_config.d/*.conf

PermitRootLogin no

PasswordAuthentication no
PermitEmptyPasswords no

KbdInteractiveAuthentication no

UsePAM no

X11Forwarding no
PrintMotd no

AuthenticationMethods publickey
AllowUsers "<JohnDoe>"
```

```bash
sudo systemctl restart ssh
```

## Client-side

ssh config:

```vim
Host asus-pn51
  HostName "<IPv4>"
  User "<JohnDoe>"
  SetEnv TERM=xterm-256color
```

```bash
ssh-keygen -t ed25519 -C "Asus PN51"
ssh-copy-id "<JohnDoe>"@"<IPv4>"

# test that these fail
ssh fake@"<IPv4>"
ssh root@"<IPv4>"

# test that these succeed
ssh "<JohnDoe>"@"<IPv4>"
ssh asus-pn51
```
