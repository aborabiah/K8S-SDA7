FROM alpine:3.18

# Install tools + download both binaries in one layer
RUN apk add --no-cache curl tar ca-certificates bash vim nano \
    && curl -sSL https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl \
       -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl \
    && curl -sSL https://github.com/GoogleCloudPlatform/kubectl-ai/releases/download/v0.0.18/kubectl-ai_Linux_x86_64.tar.gz \
       | tar -xz -C /usr/local/bin \
    && chmod +x /usr/local/bin/kubectl-ai

# Create kube directory
RUN mkdir -p /root/.kube

# Set working directory
WORKDIR /root

# Set environment variables
ENV TERM=xterm-256color
ENV KUBECONFIG=/root/.kube/config

# Set environment variables for kubectl-ai
ENV GEMINI_API_KEY=AIzaSyAus1bYeszdrau2WHY-OSJnfDSqPCqL47g

# Create kubectl-ai config directory and config file
RUN mkdir -p /root/.config/kubectl-ai && \
    echo '# LLM provider configuration' > /root/.config/kubectl-ai/config.yaml && \
    echo 'llmProvider: "gemini"' >> /root/.config/kubectl-ai/config.yaml && \
    echo 'model: "gemini-2.5-pro"' >> /root/.config/kubectl-ai/config.yaml && \
    echo 'skipVerifySSL: false' >> /root/.config/kubectl-ai/config.yaml

CMD ["/bin/sh"]