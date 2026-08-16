mod generate 'justfile.d/generate.just'
mod test 'justfile.d/test.just'
mod deploy 'justfile.d/deployment.just'

_default:
    @just -l -u --list-submodules
