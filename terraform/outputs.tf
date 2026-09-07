# Datos que necesito despues del despliegue

output "url_aplicacion" {
  description = "URL publica del Gestor Documental (a traves del balanceador)"
  value       = "http://${azurerm_public_ip.ip_balanceador.ip_address}"
}

output "ip_vm_servicios" {
  description = "IP publica de la VM de servicios (SSH, Grafana y Prometheus)"
  value       = azurerm_public_ip.ip_servicios.ip_address
}

output "ip_privada_servicios" {
  description = "IP privada de la VM de servicios (la usa la aplicacion para la BD)"
  value       = azurerm_network_interface.nic_servicios.private_ip_address
}

output "url_grafana" {
  description = "Panel de Grafana"
  value       = "http://${azurerm_public_ip.ip_servicios.ip_address}:3000"
}

output "url_prometheus" {
  description = "Interfaz de Prometheus"
  value       = "http://${azurerm_public_ip.ip_servicios.ip_address}:9090"
}
