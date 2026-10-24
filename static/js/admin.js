/* Panel: vista previa de la foto, arrastrar y soltar, y confirmación al eliminar. */
document.querySelectorAll("[data-subir-foto]").forEach(function (zona) {
    var input = zona.querySelector("input[type=file]");
    var vista = zona.querySelector(".subir-vista");
    var titulo = zona.querySelector(".subir-titulo");

    function mostrar(archivo) {
        if (!archivo) { return; }
        vista.src = URL.createObjectURL(archivo);
        vista.hidden = false;
        titulo.textContent = archivo.name;
        zona.classList.add("con-foto");
    }
    input.addEventListener("change", function () { mostrar(input.files[0]); });
    ["dragenter", "dragover"].forEach(function (e) {
        zona.addEventListener(e, function (ev) { ev.preventDefault(); zona.classList.add("arrastrando"); });
    });
    ["dragleave", "drop"].forEach(function (e) {
        zona.addEventListener(e, function () { zona.classList.remove("arrastrando"); });
    });
    zona.addEventListener("drop", function (ev) {
        ev.preventDefault();
        if (ev.dataTransfer.files.length) {
            input.files = ev.dataTransfer.files;
            mostrar(input.files[0]);
        }
    });
});

document.querySelectorAll("[data-confirmar]").forEach(function (boton) {
    boton.addEventListener("click", function (ev) {
        if (!window.confirm(boton.dataset.confirmar)) { ev.preventDefault(); }
    });
});

/* Descuentos: con el porcentaje muestra los precios con descuento, y al revés. */
document.querySelectorAll("[data-oferta]").forEach(function (caja) {
    var porcentaje = caja.querySelector("[data-porcentaje]");
    var ofertas = caja.querySelectorAll("[data-oferta-de]");
    function numero(texto) { var n = parseFloat(String(texto).replace(/[,$]/g, "")); return isFinite(n) ? n : 0; }
    function normal(input) { return numero(document.querySelector("[name=" + input.dataset.ofertaDe + "]").value); }

    function desdePorcentaje() {
        var pct = numero(porcentaje.value);
        ofertas.forEach(function (input) {
            var p = normal(input);
            input.placeholder = pct && p ? (Math.round(p * (100 - pct)) / 100).toFixed(2) : "";
        });
    }
    function desdeOfertas() {
        if (porcentaje.value) { return; }
        var mayor = 0;
        ofertas.forEach(function (input) {
            var p = normal(input), o = numero(input.value);
            if (p && o && o < p) { mayor = Math.max(mayor, Math.round((p - o) / p * 100)); }
        });
        porcentaje.placeholder = mayor ? mayor + " (calculado)" : "Ej. 20";
    }
    porcentaje.addEventListener("input", function () {
        ofertas.forEach(function (input) { input.value = ""; });  // se recalculan con el nuevo porcentaje
        desdePorcentaje();
    });
    ofertas.forEach(function (input) { input.addEventListener("input", desdeOfertas); });
    document.querySelectorAll("[name^=precio_]").forEach(function (i) { i.addEventListener("input", function () { desdePorcentaje(); desdeOfertas(); }); });
    desdePorcentaje();
    desdeOfertas();
});
