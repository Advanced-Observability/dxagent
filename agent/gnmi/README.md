# gNMI export for DxAgent

To enable gNMI exporting, set a target in `dxagent.ini` and restart the agent.
The available path for gNMI subscribe are:

* `/subservices`

   json bags, formatted as defined in [ietf-service-assurance.yang](https://github.com/ekorian/dxagent/blob/master/yang/ietf-service-assurance.yang),
   per subservice. The actual json string is base64-encoded by gRPC
   (see: base64.b64decode).
   See [YANG Modules for Service Assurance draft](https://tools.ietf.org/html/draft-claise-opsawg-service-assurance-yang-04).
   
* `/metrics`

   Last observe metric value. See res/README.md and res/metrics.csv.
   
* `/symptoms`

   Positive symptoms per subservice.
   
* `/health`

   Health score value per subservice.
   
* `/`

   All of the above


