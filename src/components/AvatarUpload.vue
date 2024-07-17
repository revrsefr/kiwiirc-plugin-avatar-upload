<template>
    <div>
        <div v-if="$parent.isSelf && user.account" class="p-avatar-upload">
            <div class="p-avatar-upload-title">
                {{ $t('plugin-avatar-upload:title') }}
            </div>
            <vue-cropper
                v-if="showCropper"
                ref="cropper"
                :src="cropperSrc"
                v-bind="cropperOptions"
                class="p-avatar-upload-cropper"
                @error="handleError"
            />
            <div v-else-if="showUploading" class="p-avatar-upload-uploading">
                {{ $t('plugin-avatar-upload:uploading') }}
            </div>
            <div v-else-if="postError" class="p-avatar-upload-error">
                {{ postError[0] === '_' ? $t('plugin-avatar-upload:' + postError.substring(1)) : postError }}
            </div>
            <div v-else-if="pendingApproval" class="p-avatar-upload-pending">
                {{ $t('plugin-avatar-upload:pending_approval') }}
            </div>
            <div class="p-avatar-upload-input">
                <button type="button" class="u-button u-button-primary" @click="chooseFile">
                    {{ $t('plugin-avatar-upload:choose') }}
                </button>
                <div class="p-avatar-upload-file-name">{{ fileName }}</div>
                <button
                    type="button"
                    class="u-button u-button-primary"
                    :style="{ visibility: showCropper ? 'visible' : 'hidden' }"
                    @click="sendImage"
                >
                    {{ $t('plugin-avatar-upload:upload') }}
                </button>
            </div>
            <input ref="file" type="file" accept="image/*" @change="handleFileChange" />
        </div>
    </div>
</template>

<script>
import VueCropper from 'vue-cropperjs';
import 'cropperjs/dist/cropper.css';
import * as config from '@/config.js';

export default {
    components: {
        VueCropper,
    },
    props: ['network', 'user'],
    data() {
        return {
            showCropper: false,
            showUploading: false,
            cropperSrc: null,
            cropperOptions: {
                viewMode: 1,
                aspectRatio: 1,
                dragMode: 'move',
            },
            fileName: '',
            postError: '',
            pendingApproval: false,  // Add this line to track pending approval status
        };
    },
    methods: {
        chooseFile() {
            this.$refs.file.value = '';
            this.$refs.file.click();
        },
        handleFileChange(event) {
            this.showCropper = false;
            this.postError = '';
            this.fileName = '';

            const file = event.target.files[0];
            if (file) {
                this.fileName = file.name || '';
                const reader = new FileReader();
                reader.onload = (e) => {
                    this.showCropper = true;
                    this.cropperSrc = e.target.result;
                };
                reader.readAsDataURL(file);
            }
        },
        handleError() {
            const cropper = this.$refs.cropper;
            cropper.destroy();
            this.showCropper = false;
            this.postError = '_invalid';
        },
        sendImage() {
            this.showUploading = true;
            this.postError = '';

            this.getExtjwtToken(this.network)
                .then(this.uploadImage)
                .catch(() => {
                    this.postError = '_token';
                    this.showUploading = false;
                });
        },
        uploadImage(token) {
            const cropper = this.$refs.cropper;
            const croppedCanvas = cropper.getCroppedCanvas({
                width: 400,
                height: 400,
            });
            cropper.destroy();
            this.showCropper = false;

            if (!croppedCanvas) {
                this.showUploading = false;
                this.postError = '_invalid';
                return;
            }

            croppedCanvas.toBlob((blob) => {
                const formData = new FormData();
                formData.append('image', blob, this.fileName); // Ensure filename is included

                fetch(config.getSetting('api_url'), {
                    method: 'POST',
                    headers: {
                        authorization: token,
                    },
                    body: formData,
                })
                    .then((response) => {
                        if (!response.ok) {
                            throw new Error();
                        }
                        this.pendingApproval = true;  // Set pending approval status
                    })
                    .catch(() => {
                        this.postError = '_error';
                    })
                    .finally(() => {
                        this.showUploading = false;
                        this.$refs.file.value = '';
                        this.fileName = '';
                    });
            }, 'image/png');
        },
        getExtjwtToken(network) {
            return new Promise((resolve, reject) => {
                let fullToken = '';

                const timeout = setTimeout(() => {
                    this.$state.$off('irc.raw.EXTJWT', callback);
                    reject();
                }, 4000);

                const callback = (command, event, eventNetwork) => {
                    if (network !== eventNetwork) {
                        return;
                    }

                    event.handled = true;
                    fullToken += event.params[event.params.length - 1];
                    if (event.params.length === 4) {
                        return;
                    }
                    clearTimeout(timeout);
                    this.$state.$off('irc.raw.EXTJWT', callback);
                    resolve(fullToken);
                };

                this.$state.$on('irc.raw.EXTJWT', callback);
                network.ircClient.raw('EXTJWT', '*');
            });
        },
    },
};
</script>

<style lang="less">
.p-avatar-upload {
    padding: 0.5em;
    border-bottom: 1px solid var(--brand-midtone);

    > input {
        display: none;
    }
}

.p-avatar-upload-title {
    font-size: 1.1em;
    font-weight: 900;
    line-height: 1.1em;
    text-align: center;
}

.p-avatar-upload-cropper {
    width: 100%;
    margin-top: 0.5em;

    .cropper-view-box {
        border-radius: 50%;
        outline: inherit !important;
        box-shadow: 0 0 0 1px #39f;
    }

    .cropper-face {
        background-color: inherit !important;
    }
}

.p-avatar-upload-uploading,
.p-avatar-upload-error,
.p-avatar-upload-pending { /* Add this line for pending status styling */
    margin-top: 0.5em;
    text-align: center;
}

.p-avatar-upload-uploading {
    padding: 0.5em;
    font-weight: 700;
    color: var(--brand-primary);
}

.p-avatar-upload-error {
    background: #ffbaba;
    border: 2px solid var(--brand-error);
}

.p-avatar-upload-pending { /* Add this block for pending status styling */
    background: #fff3cd;
    border: 2px solid var(--brand-warning);
}

.p-avatar-upload-input {
    display: flex;
    flex-direction: row;
    margin-top: 0.5em;
}

.p-avatar-upload-file-name {
    flex-grow: 1;
    align-self: center;
    margin: 0 0.5em;
    overflow-x: hidden;
    text-align: center;
    text-overflow: ellipsis;
    white-space: nowrap;
}
</style>

