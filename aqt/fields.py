# Copyright: Damien Elmes <anki@ichi2.net>
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from aqt.qt import *
import re
from anki.consts import *
import aqt
from aqt.utils import saveGeom, restoreGeom, getBase, mungeQA, \
     saveSplitter, restoreSplitter, showInfo, askUser, getText, \
     openHelp
from anki.utils import isMac, isWin
import aqt.templates

#        raise Exception("Remember to disallow media&latex refs in edit.")

# need to strip the field management code out of this

class CardLayout(QDialog):

    def __init__(self, mw, note, ord=0, parent=None):
        QDialog.__init__(self, parent or mw, Qt.Window)
        self.mw = aqt.mw
        self.parent = parent or mw
        self.note = note
        self.ord = ord
        self.col = self.mw.col
        self.mm = self.mw.col.models
        self.model = note.model()
        self.setupTabs()
        v1 = QVBoxLayout()
        v1.addWidget(self.tabs)
        self.bbox = QDialogButtonBox(QDialogButtonBox.Close)
        v1.addWidget(self.bbox)
        self.setLayout(v1)
        self.updateTabs()
        self.exec_()
        return

    def setupTabs(self):
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setMovable(True)
        add = QPushButton("+")
        add.setFixedWidth(30)
        self.tabs.setCornerWidget(add)

    def updateTabs(self):
        self.forms = []
        self.tabs.clear()
        for t in self.model['tmpls']:
            self.addTab(t)

    def addTab(self, t):
        w = QWidget()
        h = QHBoxLayout()
        h.addStretch()
        label = QLabel(_("Name:"))
        h.addWidget(label)
        edit = QLineEdit()
        edit.setFixedWidth(200)
        h.addWidget(edit)
        h.addStretch()
        v = QVBoxLayout()
        v.addLayout(h)
        l = QHBoxLayout()
        l.setMargin(0)
        l.setSpacing(3)
        left = QWidget()
        # template area
        tform = aqt.forms.template.Ui_Form()
        tform.setupUi(left)
        l.addWidget(left, 5)
        # preview area
        right = QWidget()
        pform = aqt.forms.preview.Ui_Form()
        pform.setupUi(right)
        l.addWidget(right, 5)
        v.addLayout(l)
        w.setLayout(v)
        self.tabs.addTab(w, t['name'])
        self.forms.append([tform, pform, edit])

    def old():
        self.form = aqt.forms.clayout.Ui_Dialog()
        self.form.setupUi(self)
        self.setWindowTitle(_("%s Layout") % self.model['name'])
        self.plastiqueStyle = None
        if isMac or isWin:
            self.plastiqueStyle = QStyleFactory.create("plastique")
        self.connect(self.form.buttonBox, SIGNAL("helpRequested()"),
                     self.onHelp)
        self.setupCards()
        self.setupFields()
        self.form.buttonBox.button(QDialogButtonBox.Help).setAutoDefault(False)
        self.form.buttonBox.button(QDialogButtonBox.Close).setAutoDefault(False)
        restoreSplitter(self.form.splitter, "clayout")
        restoreGeom(self, "CardLayout")
        if not self.reload(first=True):
            return
        self.exec_()


    def reload(self, first=False):
        self.cards = self.col.previewCards(self.note, self.type)
        if not self.cards:
            self.accept()
            if first:
                showInfo(_("Please enter some text first."))
            else:
                showInfo(_("The current note was deleted."))
            return
        self.fillCardList()
        self.fillFieldList()
        self.fieldChanged()
        self.readField()
        return True

    # Cards & Preview
    ##########################################################################

    def setupCards(self):
        self.updatingCards = False
        self.playedAudio = {}
        f = self.form
        if self.type == 0:
            f.templateType.setText(
                _("Templates that will be created:"))
        elif self.type == 1:
            f.templateType.setText(
                _("Templates used by note:"))
        else:
            f.templateType.setText(
                _("All templates:"))
        # replace with more appropriate size hints
        for e in ("cardQuestion", "cardAnswer"):
            w = getattr(f, e)
            idx = f.templateLayout.indexOf(w)
            r = f.templateLayout.getItemPosition(idx)
            f.templateLayout.removeWidget(w)
            w.hide()
            w.deleteLater()
            w = ResizingTextEdit(self)
            setattr(f, e, w)
            f.templateLayout.addWidget(w, r[0], r[1])
        c = self.connect
        c(f.cardList, SIGNAL("activated(int)"), self.cardChanged)
        c(f.editTemplates, SIGNAL("clicked()"), self.onEdit)
        c(f.cardQuestion, SIGNAL("textChanged()"), self.formatChanged)
        c(f.cardAnswer, SIGNAL("textChanged()"), self.formatChanged)
        c(f.alignment, SIGNAL("activated(int)"), self.saveCard)
        c(f.background, SIGNAL("clicked()"),
                     lambda w=f.background:\
                     self.chooseColour(w, "card"))
        c(f.questionInAnswer, SIGNAL("clicked()"), self.saveCard)
        c(f.allowEmptyAnswer, SIGNAL("clicked()"), self.saveCard)
        c(f.typeAnswer, SIGNAL("activated(int)"), self.saveCard)
        c(f.flipButton, SIGNAL("clicked()"), self.onFlip)
        c(f.clozectx, SIGNAL("clicked()"), self.saveCard)
        def linkClicked(url):
            QDesktopServices.openUrl(QUrl(url))
        f.preview.page().setLinkDelegationPolicy(
            QWebPage.DelegateExternalLinks)
        self.connect(f.preview,
                     SIGNAL("linkClicked(QUrl)"),
                     linkClicked)
        f.alignment.addItems(alignmentLabels().values())
        self.typeFieldNames = self.mm.fieldMap(self.model)
        s = [_("Don't ask me to type in the answer")]
        s += [_("Compare with field '%s'") % fi
              for fi in self.typeFieldNames.keys()]
        f.typeAnswer.insertItems(0, s)

    def formatToScreen(self, fmt):
        fmt = fmt.replace("}}<br>", "}}\n")
        return fmt

    def screenToFormat(self, fmt):
        fmt = fmt.replace("}}\n", "}}<br>")
        return fmt

    def onEdit(self):
        aqt.templates.Templates(self.mw, self.model, self)
        self.reload()

    def formatChanged(self):
        if self.updatingCards:
            return
        text = unicode(self.form.cardQuestion.toPlainText())
        self.card.template()['qfmt'] = self.screenToFormat(text)
        text = unicode(self.form.cardAnswer.toPlainText())
        self.card.template()['afmt'] = self.screenToFormat(text)
        self.renderPreview()

    def onFlip(self):
        q = unicode(self.form.cardQuestion.toPlainText())
        a = unicode(self.form.cardAnswer.toPlainText())
        self.form.cardAnswer.setPlainText(q)
        self.form.cardQuestion.setPlainText(a)

    def readCard(self):
        self.updatingCards = True
        t = self.card.template()
        f = self.form
        f.background.setPalette(QPalette(QColor(t['bg'])))
        f.cardQuestion.setPlainText(self.formatToScreen(t['qfmt']))
        f.cardAnswer.setPlainText(self.formatToScreen(t['afmt']))
        f.questionInAnswer.setChecked(t['hideQ'])
        f.allowEmptyAnswer.setChecked(t['emptyAns'])
        f.alignment.setCurrentIndex(t['align'])
        if t['typeAns'] is None:
            f.typeAnswer.setCurrentIndex(0)
        else:
            f.typeAnswer.setCurrentIndex(t['typeAns'] + 1)
        # model-level, but there's nowhere else to put this
        f.clozectx.setChecked(self.model['clozectx'])
        self.updatingCards = False

    def fillCardList(self):
        self.form.cardList.clear()
        cards = []
        idx = 0
        for n, c in enumerate(self.cards):
            if c.ord == self.ord:
                cards.append(_("%s (current)") % c.template()['name'])
                idx = n
            else:
                cards.append(c.template()['name'])
        self.form.cardList.addItems(cards)
        self.form.cardList.setCurrentIndex(idx)
        self.cardChanged(idx)
        self.form.cardList.setFocus()

    def cardChanged(self, idx):
        self.card = self.cards[idx]
        self.readCard()
        self.renderPreview()

    def saveCard(self):
        if self.updatingCards:
            return
        t = self.card.template()
        t['align'] = self.form.alignment.currentIndex()
        t['bg'] = unicode(
            self.form.background.palette().window().color().name())
        t['hideQ'] = self.form.questionInAnswer.isChecked()
        t['emptyAns'] = self.form.allowEmptyAnswer.isChecked()
        idx = self.form.typeAnswer.currentIndex()
        if not idx:
            t['typeAns'] = None
        else:
            t['typeAns'] = idx-1
        self.model['clozectx'] = self.form.clozectx.isChecked()
        self.renderPreview()

    def chooseColour(self, button, type="field"):
        new = QColorDialog.getColor(button.palette().window().color(), self,
                                    _("Choose Color"),
                                    QColorDialog.DontUseNativeDialog)
        if new.isValid():
            button.setPalette(QPalette(new))
            if type == "field":
                self.saveField()
            else:
                self.saveCard()

    def renderPreview(self):
        c = self.card
        styles = self.model['css']
        styles += "\n.cloze { font-weight: bold; color: blue; }"
        self.form.preview.setHtml(
            ('<html><head>%s</head><body class="%s">' %
             (getBase(self.col), c.cssClass())) +
            "<style>" + styles + "</style>" +
            mungeQA(c.q(reload=True)) +
            self.maybeTextInput() +
            "<hr>" +
            mungeQA(c.a())
            + "</body></html>")
        clearAudioQueue()
        if c.id not in self.playedAudio:
            playFromText(c.q())
            playFromText(c.a())
            self.playedAudio[c.id] = True

    def maybeTextInput(self):
        if self.card.template()['typeAns'] is not None:
            return "<center><input type=text></center>"
        return ""

    def accept(self):
        self.reject()

    def reject(self):
        return QDialog.reject(self)
        self.mm.save(self.model)
        saveGeom(self, "CardLayout")
        saveSplitter(self.form.splitter, "clayout")
        self.mw.reset()
        return QDialog.reject(self)


        modified = False
        self.mw.startProgress()
        self.col.updateProgress(_("Applying changes..."))
        reset=True
        if len(self.fieldOrdinalUpdatedIds) > 0:
            self.col.rebuildFieldOrdinals(self.model.id, self.fieldOrdinalUpdatedIds)
            modified = True
        if self.needFieldRebuild:
            modified = True
        if modified:
            self.note.model.setModified()
            self.col.flushMod()
            if self.noteedit and self.noteedit.onChange:
                self.noteedit.onChange("all")
                reset=False
        if reset:
            self.mw.reset()
        self.col.finishProgress()
        QDialog.reject(self)

    def onHelp(self):
        openHelp("CardLayout")

    # Fields
    ##########################################################################

    def setupFields(self):
        self.fieldOrdinalUpdatedIds = []
        self.updatingFields = False
        self.needFieldRebuild = False
        c = self.connect; f = self.form
        sc = SIGNAL("stateChanged(int)")
        cl = SIGNAL("clicked()")
        c(f.fieldAdd, cl, self.addField)
        c(f.fieldDelete, cl, self.deleteField)
        c(f.fieldUp, cl, self.moveFieldUp)
        c(f.fieldDown, cl, self.moveFieldDown)
        c(f.preserveWhitespace, sc, self.saveField)
        c(f.fieldUnique, sc, self.saveField)
        c(f.fieldRequired, sc, self.saveField)
        c(f.sticky, sc, self.saveField)
        c(f.fieldList, SIGNAL("currentRowChanged(int)"),
                     self.fieldChanged)
        c(f.fieldName, SIGNAL("lostFocus()"),
                     self.saveField)
        c(f.fontFamily, SIGNAL("currentFontChanged(QFont)"),
                     self.saveField)
        c(f.fontSize, SIGNAL("valueChanged(int)"),
                     self.saveField)
        c(f.fontSizeEdit, SIGNAL("valueChanged(int)"),
                     self.saveField)
        w = self.form.fontColour
        c(w, SIGNAL("clicked()"),
                     lambda w=w: self.chooseColour(w))
        c(self.form.rtl,
                     SIGNAL("stateChanged(int)"),
                     self.saveField)

    def fieldChanged(self):
        row = self.form.fieldList.currentRow()
        if row == -1:
            row = 0
        self.field = self.model['flds'][row]
        self.readField()
        self.enableFieldMoveButtons()

    def readField(self):
        fld = self.field
        f = self.form
        self.updatingFields = True
        f.fieldName.setText(fld['name'])
        f.fieldUnique.setChecked(fld['uniq'])
        f.fieldRequired.setChecked(fld['req'])
        f.fontFamily.setCurrentFont(QFont(fld['font']))
        f.fontSize.setValue(fld['qsize'])
        f.fontSizeEdit.setValue(fld['esize'])
        f.fontColour.setPalette(QPalette(QColor(fld['qcol'])))
        f.rtl.setChecked(fld['rtl'])
        f.preserveWhitespace.setChecked(fld['pre'])
        f.sticky.setChecked(fld['sticky'])
        self.updatingFields = False

    def saveField(self, *args):
        self.needFieldRebuild = True
        if self.updatingFields:
            return
        self.updatingFields = True
        fld = self.field
        # get name; we'll handle it last
        name = unicode(self.form.fieldName.text())
        if not name:
            return
        fld['uniq'] = self.form.fieldUnique.isChecked()
        fld['req'] = self.form.fieldRequired.isChecked()
        fld['font'] = unicode(
            self.form.fontFamily.currentFont().family())
        fld['qsize'] = self.form.fontSize.value()
        fld['esize'] = self.form.fontSizeEdit.value()
        fld['qcol'] = str(
            self.form.fontColour.palette().window().color().name())
        fld['rtl'] = self.form.rtl.isChecked()
        fld['pre'] = self.form.preserveWhitespace.isChecked()
        fld['sticky'] = self.form.sticky.isChecked()
        self.updatingFields = False
        if fld['name'] != name:
            self.mm.renameField(self.model, fld, name)
            # as the field name has changed, we have to regenerate cards
            self.cards = self.col.previewCards(self.note, self.type)
            self.cardChanged(0)
        self.renderPreview()
        self.fillFieldList()

    def fillFieldList(self, row = None):
        oldRow = self.form.fieldList.currentRow()
        if oldRow == -1:
            oldRow = 0
        self.form.fieldList.clear()
        n = 1
        for field in self.model['flds']:
            label = field['name']
            item = QListWidgetItem(label)
            self.form.fieldList.addItem(item)
            n += 1
        count = self.form.fieldList.count()
        if row != None:
            self.form.fieldList.setCurrentRow(row)
        else:
            while (count > 0 and oldRow > (count - 1)):
                    oldRow -= 1
            self.form.fieldList.setCurrentRow(oldRow)
        self.enableFieldMoveButtons()

    def enableFieldMoveButtons(self):
        row = self.form.fieldList.currentRow()
        if row < 1:
            self.form.fieldUp.setEnabled(False)
        else:
            self.form.fieldUp.setEnabled(True)
        if row == -1 or row >= (self.form.fieldList.count() - 1):
            self.form.fieldDown.setEnabled(False)
        else:
            self.form.fieldDown.setEnabled(True)

    def addField(self):
        f = self.mm.newField(self.model)
        l = len(self.model['flds'])
        f['name'] = _("Field %d") % l
        self.mw.progress.start()
        self.mm.addField(self.model, f)
        self.mw.progress.finish()
        self.reload()
        self.form.fieldList.setCurrentRow(l)
        self.form.fieldName.setFocus()
        self.form.fieldName.selectAll()

    def deleteField(self):
        row = self.form.fieldList.currentRow()
        if row == -1:
            return
        if len(self.model.fields) < 2:
            showInfo(_("Please add a new field first."))
            return
        if askUser(_("Delete this field and its data from all notes?")):
            self.mw.progress.start()
            self.model.delField(self.field)
            self.mw.progress.finish()
        # need to update q/a format
        self.reload()

    def moveFieldUp(self):
        row = self.form.fieldList.currentRow()
        if row == -1:
            return
        if row == 0:
            return
        self.mw.progress.start()
        self.model.moveField(self.field, row-1)
        self.mw.progress.finish()
        self.form.fieldList.setCurrentRow(row-1)
        self.reload()

    def moveFieldDown(self):
        row = self.form.fieldList.currentRow()
        if row == -1:
            return
        if row == len(self.model.fields) - 1:
            return
        self.mw.progress.start()
        self.model.moveField(self.field, row+1)
        self.mw.progress.finish()
        self.form.fieldList.setCurrentRow(row+1)
        self.reload()