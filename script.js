function mostrarIframe(src, altura = "800", ancho = "100%", containerId = "iframeContainer") {
  var container = document.getElementById(containerId);
  if (container) {
    container.innerHTML = `<iframe src="${src}" style="width:${ancho}; height:${altura}px; border:0;" allowfullscreen></iframe>`;
  } else {
    console.error("No se encontró el contenedor con ID:", containerId);
  }
}

