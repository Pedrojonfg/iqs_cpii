Public API (Reference)
======================

En esta documentación, “API pública” significa **las clases/funciones/módulos pensados para ser usados desde fuera del paquete**.
En Python, suele entenderse como:

- Elementos **sin guion bajo** (no empiezan por `_`)
- Interfaces que el proyecto considera **estables y soportadas** para que otros las importen y usen

Aquí documentamos los módulos “de cara a usuario” dentro de `iqs`.

.. toctree::
   :maxdepth: 2

   broker
   calibrator
   execution
   fundamental
   manager
   news
   nlp_veto
   technical

