Public API (Reference)
======================

In this documentation, “public API” means **the classes/functions/modules intended to be used from outside the package**.
In Python, this is typically understood as:

- **Non-underscore** elements (do not start with `_`)
- Interfaces the project considers **stable and supported** for external imports and usage

Here we document the user-facing modules within `iqs`.

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

