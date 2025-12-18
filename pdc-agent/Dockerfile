FROM grafana/pdc-agent:latest

# Install OpenSSH client for ARM64
USER root
RUN apk add --no-cache openssh-client

# Switch back to non-root user if the base image uses one
USER nobody
