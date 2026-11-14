import os, datetime, ipaddress
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

os.makedirs("./certs", exist_ok=True)

def generate_tls_certs():
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"EdgeRootCA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject).issuer_name(ca_subject)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"localhost")])
    san = x509.SubjectAlternativeName([
        x509.DNSName(u"localhost"), x509.DNSName(u"mosquitto"),
        x509.DNSName(u"edge_mosquitto"), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))
    ])
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_subject).issuer_name(ca_subject)
        .public_key(server_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(san, critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    with open("./certs/ca.crt", "wb") as f: f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
    with open("./certs/server.crt", "wb") as f: f.write(server_cert.public_bytes(serialization.Encoding.PEM))
    with open("./certs/server.key", "wb") as f:
        f.write(server_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    print("[OK] Da tao xong ca.crt, server.crt, server.key trong ./certs/")

if __name__ == "__main__":
    generate_tls_certs()
