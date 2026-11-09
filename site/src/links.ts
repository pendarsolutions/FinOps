/** Where the site sends people. Change INSTALL_URL to this site's own /install.sh once it serves one. */
export const REPO = "https://github.com/pendarsolutions/FinOps";
export const RELEASES = `${REPO}/releases`;
export const GUIDE = `${REPO}/blob/main/docs/installation.md`;
export const LICENSE = `${REPO}/blob/main/LICENSE`;
export const INSTALL_URL = `${REPO}/releases/latest/download/install.sh`;
export const INSTALL_COMMAND = `curl -fsSL ${INSTALL_URL} | sudo bash`;
