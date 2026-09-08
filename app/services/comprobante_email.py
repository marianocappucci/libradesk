"""El correo saliente de los comprobantes de LibraDesk.

🔑 **La resolucion del SMTP no se escribe aca**: sale de
`libracore.facturas_router.smtp_efectivo` sobre el MISMO resolver que ya usan
la recuperacion de contrasena (`PasswordResetService`) y el boton *Probar
conexion* (`build_smtp_probe_router`). Los tres tienen que dar lo mismo — un
producto donde el boton prueba un servidor y los mails salen por otro es
exactamente el bug que `smtp_efectivo` vino a cerrar en Contalibra.

**Por que el envio es el de LibraCore y no el de libraauth**: el de libraauth
manda texto plano (es el del mail de recuperacion) y un comprobante va con el
PDF adjunto. `libracore.email_sender.enviar_documento` adjunta, y este producto
ya depende de LibraCore para el dominio y los PDF de los comprobantes.
"""
from libracore import email_sender
from libracore.facturas_router import smtp_efectivo


def smtp_configurado(resolver) -> bool:
    """Minimo para poder mandar: servidor y usuario.

    Mismo criterio que el helper de Contalibra y que la guarda del boton de
    probar conexion, para que las tres pantallas digan lo mismo.
    """
    smtp = smtp_efectivo(resolver)
    return bool(smtp["host"] and smtp["user"])


def enviar_documento(resolver, *, to_email: str, to_name: str, pdf_path: str,
                     asunto: str, cuerpo: str) -> None:
    """Manda un PDF adjunto por el SMTP efectivo de la instancia.

    Levanta lo que levante `smtplib`; quien llama decide como se traduce (el
    router lo convierte en 502).
    """
    smtp = smtp_efectivo(resolver)
    email_sender.enviar_documento(
        to_email=to_email,
        to_name=to_name,
        pdf_path=pdf_path,
        asunto=asunto,
        cuerpo=cuerpo,
        smtp_host=smtp["host"],
        smtp_port=smtp["port"],
        smtp_user=smtp["user"],
        smtp_password=smtp["password"],
        from_email=smtp["from_email"],
        from_name=smtp["from_name"],
    )
