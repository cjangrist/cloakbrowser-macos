variable "UPSTREAM_SHA" {
  default = "unknown"
}

variable "UPSTREAM_CONTEXT" {
  default = "./upstream"
}

variable "IMAGE_NAME" {
  default = "ghcr.io/cjangrist/cloakbrowser-macos"
}

group "default" {
  targets = ["release"]
}

target "upstream" {
  context = "${UPSTREAM_CONTEXT}"
  dockerfile = "Dockerfile"
}

target "release" {
  context = "."
  dockerfile = "Dockerfile"
  contexts = {
    upstream-source = "target:upstream"
  }
  args = {
    UPSTREAM_SHA = "${UPSTREAM_SHA}"
  }
  platforms = ["linux/amd64"]
  tags = [
    "${IMAGE_NAME}:latest",
    "${IMAGE_NAME}:upstream-${UPSTREAM_SHA}",
  ]
  attest = [
    "type=provenance,mode=max",
    "type=sbom",
  ]
}

target "test" {
  inherits = ["release"]
  platforms = ["linux/amd64"]
  tags = ["cloakbrowser-macos:test"]
  attest = []
}
