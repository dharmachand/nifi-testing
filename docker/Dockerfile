FROM apache/nifi:1.15.3

USER root

RUN apt-get update
RUN apt-get install openjdk-11-jdk -y
RUN apt-get install jq
RUN wget https://releases.hashicorp.com/vault/1.14.2/vault_1.14.2_linux_amd64.zip
RUN unzip vault_1.14.2_linux_amd64.zip
RUN chown root:root vault
RUN mv vault /usr/local/bin/
RUN rm vault_1.14.2_linux_amd64.zip

COPY vault/* .
RUN mkdir out
RUN sed -i 's/127.0.0.1:8200/vault:8200/g' vault-agent-config.hcl
RUN sed -i 's/127.0.0.1:8200/vault:8200/g' configure-vault.sh
RUN sed -i 's/^M//g; s/\r//g' *.sh
RUN chmod +x *.sh

ENV JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64/

RUN echo "\njava.arg.debug=-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:8000\njava.arg.21=-Dvault.transit.key=non-prod\njava.arg.22=-Dvault.transit.api=/v1/nifi/\n" >>/opt/nifi/nifi-current/conf/bootstrap.conf

#uncomment if using real vault
RUN echo "java.arg.20=-Dvault-agent.url=http://127.0.0.1:8007\n" >>/opt/nifi/nifi-current/conf/bootstrap.conf
#or, if using wiremocks instead of vault
RUN echo "java.arg.20=-Dvault-agent.url=http://wiremock:8080\n" >>/opt/nifi/nifi-current/conf/bootstrap.conf

ENTRYPOINT ["./start_vault_agent_nifi.sh"]