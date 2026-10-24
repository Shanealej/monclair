/* Muestra el barrio solo en Managua y calcula el envío al instante. */
(function () {
    var cfg = JSON.parse(document.getElementById("config-envio").textContent);
    var ciudad = document.querySelector("[name=ciudad]");
    var barrio = document.querySelector("[name=barrio]");
    var campoBarrio = document.getElementById("campo-barrio");
    var tipoEl = document.getElementById("envio-tipo");
    var valorEl = document.getElementById("envio-valor");
    var totalEl = document.getElementById("total-valor");
    function fmt(n) { return cfg.moneda + " " + n.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: n % 1 ? 2 : 0 }); }

    function actualizar() {
        var esManagua = ciudad.value === "Managua";
        campoBarrio.hidden = !esManagua;
        barrio.required = esManagua;
        var tipo = "Envío", estado = "pendiente", texto = "Se calcula según tu ciudad", monto = null, precio;
        if (cfg.gratis) {
            estado = "gratis"; texto = "Gratis"; monto = 0;
        } else if (ciudad.value) {
            tipo = esManagua ? "Delivery en Managua" : "Cargo de transporte";
            if (esManagua && !barrio.value) {
                texto = "Elige tu barrio";
            } else {
                precio = esManagua ? cfg.barrios[barrio.value] : cfg.transporte;
                if (precio === null || precio === undefined) { estado = "confirmar"; texto = "Por confirmar"; }
                else { estado = "calculado"; texto = fmt(precio); monto = precio; }
            }
        }
        tipoEl.textContent = tipo;
        valorEl.textContent = texto;
        valorEl.className = "envio-" + estado;

        totalEl.innerHTML = "";
        var s = document.createElement("strong");
        s.textContent = fmt(cfg.subtotal + (monto || 0));
        totalEl.appendChild(s);
        if (estado === "confirmar") {
            var n = document.createElement("small");
            n.textContent = "+ envío por confirmar";
            totalEl.appendChild(n);
        }
    }
    ciudad.addEventListener("change", actualizar);
    barrio.addEventListener("change", actualizar);
    actualizar();
})();
