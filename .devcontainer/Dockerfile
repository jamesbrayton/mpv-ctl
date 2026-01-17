# Dockerfile for Development Environment
FROM ubuntu:noble
# FROM debian:trixie

# Metadata
LABEL maintainer="jamesgbrayton@gmail.com"
LABEL description="Base development environment for projects"
LABEL version="1.0"

# Create a non-root user for development
ARG USERNAME=vscode
ENV USERNAME=${USERNAME}

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install base system dependencies
# Install additional useful tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    unzip \
    git \
    build-essential \
    ca-certificates \
    gnupg \
    software-properties-common \
    ncurses-bin \
    zsh \
    fonts-powerline \
    locales \
    sudo \
    openssh-server \
    openssh-client \
    tmux \ 
    screen \
    libncurses5-dev \
    libncursesw5-dev \
    terminfo \
    vim \
    nano \
    htop \
    tree \
    rsync \
    libnss3 \
    nodejs \
    npm \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && ln -s /usr/bin/python3 /usr/bin/python \
    && locale-gen en_US.UTF-8

# Configure terminal environment for remote development
ENV TERM=xterm-256color
ENV COLORTERM=truecolor

# Configure SSG server for stable remote development
RUN mkdir -p /run/sshd && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication no/PasswordAuthentication no/' /etc/ssh/sshd_config && \
    sed -i 's/#PublicKeyAuthentication yes/PublicKeyAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/X11Forwarding yes/X11Forwarding no/' /etc/ssh/sshd_config

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update && \
    apt-get install -y gh && \
    rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install uv (modern Python package manager)
# Copy from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install Python 3.13 using uv so that we have a hot loaded python environment
RUN uv python install 3.13

# Install Pyright language server globally
RUN npm install -g pyright

# Create non-root user with sudo access
RUN useradd -l -m -s /bin/zsh $USERNAME && \
    echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME

# Create workspace directory and set permissions
RUN mkdir -p /workspace && \
    chown -R $USERNAME:$USERNAME /home/$USERNAME /workspace

# Switch to developer user for oh-my-zsh installation
USER $USERNAME
WORKDIR /home/$USERNAME

# Install oh-my-zsh
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended && \
    sed -i 's/ZSH_THEME="robbyrussell"/ZSH_THEME="agnoster"/g' /home/$USERNAME/.zshrc

# Install Claude CLI
RUN curl -fsSL https://claude.ai/install.sh | bash

# Set up environment variables in .zshrc
RUN echo "export PATH=$PATH:\$HOME/.local/bin:\$HOME/.cargo/bin" >> /home/$USERNAME/.zshrc

# Set working directory
WORKDIR /workspace

# Verify all installations (allow failures for optional tools)
RUN echo "=== Environment Verification ==="

# Set default shell to ZSH
CMD ["/bin/zsh"]
