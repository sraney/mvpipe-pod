# Clean MiniMax H3 RunPod image

This candidate packages ComfyUI **0.46.0**, Python **3.12**, PyTorch **2.11.0+cu130**,
and the three pinned H3 helper packages: KJNodes, VideoHelperSuite, and the H3 latent
upscaler. The same software versions passed the included cat-and-yarn H3 test on an
RTX PRO 6000 Blackwell. The newly built Docker image still needs its own GPU test.

## Storage and startup

| Location | Contents |
| --- | --- |
| `/opt/ComfyUI` | Image-owned application and custom nodes |
| `/opt/venv` | Image-owned Python environment |
| `/workspace/models` | Existing shared model library |
| `/workspace/user` | Persistent workflows and settings |
| `/workspace/input`, `/workspace/output` | Persistent media |
| `/workspace/logs` | Runtime logs |
| `/tmp/comfyui`, `/run/mvpipe` | Disposable temporary files and process state |

One supervisor owns one ComfyUI process. The volume's start/stop/restart/status scripts
are routed to that supervisor on boot; previous scripts are backed up once. Stopping
or restarting refuses while work is active or queued. A stopped worker stays stopped
until started; restarting the container starts a new worker normally.

No packages, git updates, model downloads, or output deletions occur at boot.
Models are excluded from the image. Keep the existing network volume.
This minimal image does not include JupyterLab, the transport agent, an idle-stop
watchdog, or the older multi-GPU worker arrangement. If those services are required,
add and validate them explicitly before replacing the existing deployment.

## 1. Upload the prepared update using GitHub

1. Open `sraney/mvpipe-pod` and select the branch menu, currently `main`.
2. Create a branch named `h3-stable-image` from `main`.
3. Extract the supplied update ZIP on your computer. Inside is `mvpipe-pod-update`.
4. On your new GitHub branch, choose **Add file → Upload files**.
5. Drag the **contents** of `mvpipe-pod-update` into the upload area, including
   `.github`, `pod-template`, and `.gitattributes`. Do not upload the ZIP itself or its
   enclosing directory. The files must replace the matching repository paths.
6. Check that the proposed paths include `.github/workflows/build-pod-image.yml`
   and `pod-template/Dockerfile`, then commit to `h3-stable-image`.
7. Open a pull request for review. Its build checks do not publish an image.

The prepared update only includes changed/new files. Existing files not included
in the ZIP remain in the repository. The active workflow is the file under `.github`;
do not copy the old `pod-template/github-actions-build.yml` example over it.

## 2. Build a candidate using GitHub Actions

After reviewing and merging the update:

1. Open **Actions → build-pod-image → Run workflow**.
2. Select `main`; use candidate tag **h3-stable-candidate** and start the run.
3. Wait for all steps to pass. The workflow checks process controls, builds Linux amd64,
   checks Python dependencies, and performs CPU-only ComfyUI startup before publishing.
4. Read the run summary. It lists the candidate tag, source revision tag, and image digest.
   The candidate will be `ghcr.io/sraney/mvpipe-pod:h3-stable-candidate`.
5. Copy the immutable `ghcr.io/sraney/mvpipe-pod@sha256:...` reference for deployment.

The workflow never overwrites `latest`. If the runner runs out of disk, use a larger
GitHub runner rather than dropping checks or downloading dependencies at pod boot.

Publishing uses GitHub's built-in workflow token. In repository **Settings → Actions →
General**, ensure Actions are enabled and permitted to publish packages. Existing
package **Manage Actions access** must allow this repository write access if needed.
For unauthenticated RunPod pulls, set the container package visibility to Public.
Otherwise configure a RunPod registry credential with permission to read the package.

## 3. Create a separate RunPod test template

| Setting | Value |
| --- | --- |
| Name | `mvpipe-h3-stable-test` |
| Container image | Digest copied from the successful GitHub run |
| Container disk | 60 GB |
| Volume mount path | `/workspace` |
| HTTP ports | `8188` |
| TCP ports | `22` |
| Container start command | Empty; use the image default |
| GPU count | One |

Use a host/driver compatible with CUDA 13.0. The live Blackwell pod's driver was
verified with this runtime; do not assume every available RunPod host matches it.
Deploy in the data center containing your **existing network volume**, and attach
that volume. Do not create an empty replacement volume or download the models again.

Set **PUBLIC_KEY** to your existing SSH public key. Never upload its private key.
Alternatively, the image reads public keys from `/workspace/mvpipe/authorized_keys`.
For test isolation set these environment variables:

| Variable | Value |
| --- | --- |
| `COMFYUI_USER_DIRECTORY` | `/workspace/user-image-test` |
| `COMFYUI_OUTPUT_DIRECTORY` | `/workspace/output/image-test` |

The test deployment shares models but uses a separate user database and output
directory. Its boot refreshes the convenience control scripts; run them only on the
pod you intend to control. Keep the current pod available until validation succeeds.

## 4. Verify the new image

1. Open RunPod's ComfyUI connection on port 8188. Check the pod logs for startup,
   and `/workspace/logs/comfyui-gpu0.log` for detailed execution logs.
2. Load `validation/cat-yarn-workflow.json` from this repository in ComfyUI.
3. Run it. All four model files are already on the shared model volume.
4. Watch the saved clip and confirm the cat plays with the yarn ball without errors.
5. Restart the test pod, then verify the image version, model discovery, saved workflow,
   and another successful render. No package installation should run during startup.

GitHub's ordinary hosted runner does not prove GPU inference works. This test is the
acceptance gate even when the build is green.

## 5. Promote and roll back

Once the candidate passes, use that exact digest in your normal RunPod template.
Remove the two test-isolation variables to restore `/workspace/user` and
`/workspace/output`. Keep the previous working template and its image digest.
Do not rely on a movable `latest` tag for rollback.

The new image replaces the application from its own immutable layers at every
container start. Models, workflows, and user data remain on the network volume.
Do not delete older persistent installs until their remaining useful files are inventoried.
