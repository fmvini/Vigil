# Certificados exclusivos dos testes

CA e certificado/chave do servidor local de `test_transport_sockets.py`.
A chave é um fixture público, sem uso ou autorização em produção. Não instalar
esta CA no sistema, nos containers ou no transporte runtime. O teste carrega a
CA apenas no SSLContext da instância criada por ele, mantendo CERT_REQUIRED e
check_hostname. Certificado válido somente para `sockets.example.com`.

Gerados com OpenSSL 3.5.5 em 2026-10-04, validade de 3650 dias. Ao renovar,
preservar SAN, serverAuth e keyUsage/basicConstraints; descartar a chave da CA.
Os testes rejeitam tanto CA desconhecida quanto hostname incorreto.
