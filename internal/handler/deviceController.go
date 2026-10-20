package handler

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/gorilla/mux"
	libp2pcrypto "github.com/libp2p/go-libp2p/core/crypto"
	libp2ppeer "github.com/libp2p/go-libp2p/core/peer"
	"github.com/silicium/internal/models"
	"gorm.io/gorm"
)

const devicePairingLifetime = 10 * time.Minute

var deviceNodeIDPattern = regexp.MustCompile(`^[A-Za-z0-9._-]{1,64}$`)

type pairDeviceRequest struct {
	Code      string `json:"code"`
	NodeID    string `json:"nodeId"`
	PeerID    string `json:"peerId"`
	PublicKey string `json:"publicKey"`
	Signature string `json:"signature"`
}

func (h *Handler) ListUserDevices(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session n’est pas valide."})
		return
	}
	var devices []models.UserDevice
	if err := h.DB.WithContext(r.Context()).Where("user_id = ?", userID).Order("linked_at DESC, id DESC").Find(&devices).Error; err != nil {
		writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "Les appareils du compte sont indisponibles."})
		return
	}
	writeAuthJSON(w, http.StatusOK, map[string]any{"items": devices})
}

func (h *Handler) CreateDevicePairingCode(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session n’est pas valide."})
		return
	}
	secret := make([]byte, 32)
	if _, err := rand.Read(secret); err != nil {
		writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "Le code d’association ne peut pas être créé."})
		return
	}
	code := hex.EncodeToString(secret)
	digest := sha256.Sum256([]byte(code))
	now := time.Now().UTC()
	challenge := models.DevicePairingCode{
		UserID: userID, CodeHash: hex.EncodeToString(digest[:]), ExpiresAt: now.Add(devicePairingLifetime),
	}
	err := h.DB.WithContext(r.Context()).Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("user_id = ? AND (consumed_at IS NOT NULL OR expires_at <= ?)", userID, now).
			Delete(&models.DevicePairingCode{}).Error; err != nil {
			return err
		}
		if err := tx.Where("user_id = ? AND consumed_at IS NULL", userID).Delete(&models.DevicePairingCode{}).Error; err != nil {
			return err
		}
		return tx.Create(&challenge).Error
	})
	if err != nil {
		writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "Le code d’association ne peut pas être créé."})
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeAuthJSON(w, http.StatusCreated, map[string]any{"code": code, "expiresAt": challenge.ExpiresAt})
}

func (h *Handler) PairDevice(w http.ResponseWriter, r *http.Request) {
	var req pairDeviceRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10)).Decode(&req); err != nil {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La preuve d’association est invalide."})
		return
	}
	req.Code = strings.TrimSpace(req.Code)
	req.NodeID = strings.TrimSpace(req.NodeID)
	req.PeerID = strings.TrimSpace(req.PeerID)
	if len(req.Code) != 64 || !deviceNodeIDPattern.MatchString(req.NodeID) || len(req.PeerID) == 0 || len(req.PeerID) > 128 {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "Le code ou l’identité de l’appareil est invalide."})
		return
	}
	codeBytes, err := hex.DecodeString(req.Code)
	if err != nil || len(codeBytes) != 32 {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "Le code d’association est invalide."})
		return
	}
	publicBytes, err := base64.StdEncoding.DecodeString(strings.TrimSpace(req.PublicKey))
	if err != nil {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "L’identité cryptographique de l’appareil est invalide."})
		return
	}
	publicKey, err := libp2pcrypto.UnmarshalPublicKey(publicBytes)
	if err != nil || publicKey.Type() != libp2pcrypto.Ed25519 {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "Cette identité d’appareil n’est pas prise en charge."})
		return
	}
	derivedPeerID, err := libp2ppeer.IDFromPublicKey(publicKey)
	if err != nil || derivedPeerID.String() != req.PeerID {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La clé ne correspond pas à l’identité du nœud."})
		return
	}
	signature, err := hex.DecodeString(strings.TrimSpace(req.Signature))
	if err != nil || len(signature) != 64 {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La signature de l’appareil est invalide."})
		return
	}
	if valid, verifyErr := publicKey.Verify(devicePairingPayload(req.Code, req.NodeID, req.PeerID), signature); verifyErr != nil || !valid {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La signature ne prouve pas le contrôle de cet appareil."})
		return
	}
	codeHash := devicePairingCodeHash(req.Code)
	now := time.Now().UTC()
	var linked models.UserDevice
	err = h.DB.WithContext(r.Context()).Transaction(func(tx *gorm.DB) error {
		var pairing models.DevicePairingCode
		if err := tx.Where("code_hash = ?", codeHash).First(&pairing).Error; err != nil {
			return errors.New("pairing_code_invalid")
		}
		if pairing.ConsumedAt != nil || !pairing.ExpiresAt.After(now) {
			return errors.New("pairing_code_expired")
		}
		consumed := tx.Model(&models.DevicePairingCode{}).
			Where("id = ? AND consumed_at IS NULL AND expires_at > ?", pairing.ID, now).
			Update("consumed_at", now)
		if consumed.Error != nil {
			return consumed.Error
		}
		if consumed.RowsAffected != 1 {
			return errors.New("pairing_code_expired")
		}

		var byPeer models.UserDevice
		peerErr := tx.Where("peer_id = ?", req.PeerID).First(&byPeer).Error
		if peerErr != nil && !errors.Is(peerErr, gorm.ErrRecordNotFound) {
			return peerErr
		}
		var byNode models.UserDevice
		nodeErr := tx.Where("node_id = ?", req.NodeID).First(&byNode).Error
		if nodeErr != nil && !errors.Is(nodeErr, gorm.ErrRecordNotFound) {
			return nodeErr
		}
		hasPeer := peerErr == nil
		hasNode := nodeErr == nil
		if hasPeer && hasNode && byPeer.ID != byNode.ID {
			return errors.New("device_identity_conflict")
		}
		if hasPeer || hasNode {
			existing := byPeer
			if !hasPeer {
				existing = byNode
			}
			if existing.UserID != pairing.UserID {
				return errors.New("device_already_linked")
			}
			existing.NodeID = req.NodeID
			existing.PeerID = req.PeerID
			existing.LinkedAt = now
			if err := tx.Save(&existing).Error; err != nil {
				return err
			}
			linked = existing
			return nil
		}
		linked = models.UserDevice{UserID: pairing.UserID, NodeID: req.NodeID, PeerID: req.PeerID, LinkedAt: now}
		return tx.Create(&linked).Error
	})
	if err != nil {
		switch err.Error() {
		case "pairing_code_invalid":
			writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "Le code d’association est invalide ou déjà utilisé."})
		case "pairing_code_expired":
			writeAuthJSON(w, http.StatusGone, map[string]string{"message": "Le code d’association a expiré. Générez-en un nouveau."})
		case "device_already_linked":
			writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Cet appareil est déjà associé à un autre compte."})
		case "device_identity_conflict":
			writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Les identités de cet appareil correspondent à plusieurs associations existantes."})
		default:
			writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "L’appareil n’a pas pu être associé."})
		}
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeAuthJSON(w, http.StatusOK, map[string]any{"device": linked})
}

func (h *Handler) UnlinkUserDevice(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session n’est pas valide."})
		return
	}
	id, err := strconv.ParseUint(strings.TrimSpace(mux.Vars(r)["id"]), 10, 64)
	if err != nil || id == 0 {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "L’identifiant de l’appareil est invalide."})
		return
	}
	result := h.DB.WithContext(r.Context()).Where("id = ? AND user_id = ?", id, userID).Delete(&models.UserDevice{})
	if result.Error != nil {
		writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "L’appareil n’a pas pu être dissocié."})
		return
	}
	if result.RowsAffected == 0 {
		writeAuthJSON(w, http.StatusNotFound, map[string]string{"message": "Cet appareil n’appartient pas à ce compte."})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func devicePairingPayload(code, nodeID, peerID string) []byte {
	return []byte(fmt.Sprintf("silicium-device-link-v1\n%s\n%s\n%s", code, nodeID, peerID))
}

func devicePairingCodeHash(code string) string {
	digest := sha256.Sum256([]byte(code))
	return hex.EncodeToString(digest[:])
}
